const childProcess = require("child_process");
const fs = require("fs");
const path = require("path");
const vscode = require("vscode");

function activate(context) {
    const provider = new LimbiSidebarProvider(context);

    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider("limbi.sidebar", provider, {
            webviewOptions: { retainContextWhenHidden: true },
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand("limbi.openPanel", async () => {
            await vscode.commands.executeCommand("workbench.view.extension.limbi");
            provider.focus();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand("limbi.askAboutSelection", async () => {
            await vscode.commands.executeCommand("workbench.view.extension.limbi");
            provider.focus();
            const selectionContext = getSelectionContext();
            if (!selectionContext) {
                vscode.window.showInformationMessage("Open a file and select some code first.");
                return;
            }

            provider.postMessage({
                type: "draftPrompt",
                prompt: buildSelectionPrompt(selectionContext),
            });
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand("limbi.refreshAgents", async () => {
            await provider.refreshState();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand("limbi.generateMcpConfig", async () => {
            const folder = vscode.workspace.workspaceFolders?.[0];
            if (!folder) {
                vscode.window.showErrorMessage("Open the Limbi project folder or limbi-vscode folder in VS Code to generate an MCP config.");
                return;
            }

            const projectRoot = findLimbiProjectRoot(folder.uri.fsPath, context.extensionUri.fsPath);
            if (!projectRoot) {
                vscode.window.showErrorMessage("Could not find the Limbi repository root. Open the main Limbi repository or the limbi-vscode folder.");
                return;
            }

            const vscodeDir = path.join(projectRoot, ".vscode");
            fs.mkdirSync(vscodeDir, { recursive: true });

            const configPath = path.join(vscodeDir, "mcp.json");
            const pythonCommand = await resolvePythonCommand(String(getConfig("pythonCommand") || "python"));
            const config = {
                servers: {
                    limbi: {
                        type: "stdio",
                        command: pythonCommand,
                        args: ["-m", "limbi.mcp_server"],
                    },
                },
            };

            fs.writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`, "utf8");
            vscode.window.showInformationMessage(`Limbi MCP config written to ${configPath} using ${pythonCommand}`);
        })
    );
}

function deactivate() {}

function findLimbiProjectRoot(workspaceRoot, extensionRoot) {
    const candidates = [
        workspaceRoot,
        path.dirname(workspaceRoot),
        extensionRoot,
        path.dirname(extensionRoot),
    ];
    const seen = new Set();

    for (const candidate of candidates) {
        if (!candidate || seen.has(candidate)) {
            continue;
        }
        seen.add(candidate);

        if (
            fs.existsSync(path.join(candidate, "pyproject.toml")) &&
            fs.existsSync(path.join(candidate, "limbi", "mcp_server.py"))
        ) {
            return candidate;
        }
    }

    return undefined;
}

class LimbiSidebarProvider {
    constructor(context) {
        this._context = context;
        this._view = undefined;
    }

    resolveWebviewView(webviewView) {
        this._view = webviewView;
        const webview = webviewView.webview;
        webview.options = {
            enableScripts: true,
            localResourceRoots: [vscode.Uri.joinPath(this._context.extensionUri, "media")],
        };
        webview.html = this._getHtml(webview);

        webview.onDidReceiveMessage(async (message) => {
            switch (message.type) {
                case "ready":
                    await this.refreshState();
                    break;
                case "sendPrompt":
                    await this.handlePrompt(message.prompt || "");
                    break;
                case "refresh":
                    await this.refreshState();
                    break;
                case "clearChat":
                    await this.clearChat();
                    break;
                case "selectionPrompt":
                    await this.handleSelectionPrompt();
                    break;
            }
        });
    }

    focus() {
        if (this._view) {
            this._view.show?.(true);
        }
    }

    postMessage(message) {
        if (this._view) {
            this._view.webview.postMessage(message);
        }
    }

    async refreshState() {
        const [health, agents] = await Promise.all([
            fetchJson("/health").catch((error) => ({ error: String(error) })),
            fetchJson("/api/agents").catch((error) => ({ error: String(error) })),
        ]);

        this.postMessage({
            type: "state",
            health,
            agents,
        });
    }

    async clearChat() {
        try {
            await fetchJson("/api/chat/clear", { method: "POST" });
            this.postMessage({ type: "chatCleared" });
        } catch (error) {
            this.postMessage({ type: "error", error: String(error) });
        }
    }

    async handleSelectionPrompt() {
        const selectionContext = getSelectionContext();
        if (!selectionContext) {
            this.postMessage({
                type: "error",
                error: "Open a file and select code before sending a selection-aware prompt.",
            });
            return;
        }

        this.postMessage({
            type: "draftPrompt",
            prompt: buildSelectionPrompt(selectionContext),
        });
    }

    async handlePrompt(rawPrompt) {
        const prompt = String(rawPrompt || "").trim();
        if (!prompt) {
            return;
        }

        let finalPrompt = prompt;
        if (getConfig("includeSelectionByDefault")) {
            const selectionContext = getSelectionContext();
            if (selectionContext) {
                finalPrompt = `${prompt}\n\n${buildSelectionContextBlock(selectionContext)}`;
            }
        }

        this.postMessage({ type: "chatPending", prompt });

        try {
            const response = await fetchJson("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: finalPrompt, stream: false }),
            });

            this.postMessage({
                type: "chatResult",
                prompt,
                response,
            });
            await this.refreshState();
        } catch (error) {
            this.postMessage({ type: "error", error: String(error) });
        }
    }

    _getHtml(webview) {
        const cssUri = webview.asWebviewUri(vscode.Uri.joinPath(this._context.extensionUri, "media", "main.css"));
        const jsUri = webview.asWebviewUri(vscode.Uri.joinPath(this._context.extensionUri, "media", "main.js"));
        const nonce = String(Date.now());

        return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${webview.cspSource} https: data:; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="stylesheet" href="${cssUri}" />
  <title>Limbi</title>
</head>
<body>
  <div class="shell">
    <header class="hero">
      <div>
        <div class="eyebrow">Limbi</div>
        <h1>Agentic coding sidekick</h1>
        <p>Use the running Limbi backend from inside VS Code and expose the same agent swarm through MCP.</p>
      </div>
      <div class="status-card">
        <div class="status-label">Backend</div>
        <div id="status-text">Checking...</div>
        <div id="status-subtext">Waiting for /health</div>
      </div>
    </header>

    <section class="actions">
      <button id="refresh-btn">Refresh</button>
      <button id="selection-btn">Use Selection</button>
      <button id="clear-btn" class="ghost">Clear Chat</button>
    </section>

    <section class="composer">
      <label for="prompt-input">Prompt</label>
      <textarea id="prompt-input" rows="5" placeholder="Ask Limbi to route work, analyze code, or invoke specific agents..."></textarea>
      <button id="send-btn" class="send">Send to Limbi</button>
    </section>

    <section class="messages">
      <div class="section-title">Conversation</div>
      <div id="messages"></div>
    </section>

    <section class="agents">
      <div class="section-title">Registered Agents</div>
      <div id="agents-list" class="agents-list"></div>
    </section>
  </div>

  <script nonce="${nonce}" src="${jsUri}"></script>
</body>
</html>`;
    }
}

function getConfig(key) {
    return vscode.workspace.getConfiguration("limbi").get(key);
}

async function resolvePythonCommand(configuredCommand) {
    if (!getConfig("resolveShellEnvironment")) {
        return configuredCommand;
    }

    const resolvedCommand = await Promise.resolve(resolveCommandFromEnvironment(configuredCommand));
    return resolvedCommand || configuredCommand;
}

function resolveCommandFromEnvironment(command) {
    const trimmed = String(command || "").trim();
    if (!trimmed) {
        return "";
    }

    if (isExplicitCommandPath(trimmed)) {
        return trimmed;
    }

    const fromPath = findExecutableOnPath(trimmed);
    if (fromPath) {
        return fromPath;
    }

    return resolveCommandFromShell(trimmed);
}

function isExplicitCommandPath(command) {
    return path.isAbsolute(command) || command.includes("/") || command.includes("\\");
}

function findExecutableOnPath(command) {
    const pathValue = process.env.PATH || "";
    const pathEntries = pathValue.split(path.delimiter).filter(Boolean);
    const extensions = process.platform === "win32"
        ? (process.env.PATHEXT || ".EXE;.CMD;.BAT;.COM").split(";").filter(Boolean)
        : [""];

    for (const entry of pathEntries) {
        for (const extension of extensions) {
            const candidate = path.join(entry, `${command}${extension}`);
            if (fs.existsSync(candidate)) {
                return candidate;
            }
        }
    }

    return "";
}

function resolveCommandFromShell(command) {
    if (process.platform === "win32") {
        return resolveCommandWithTool("where.exe", [command]);
    }

    const shell = process.env.SHELL || "/bin/bash";
    return resolveCommandWithTool(shell, ["-ilc", `command -v ${shellQuote(command)}`]);
}

function resolveCommandWithTool(executable, args) {
    try {
        const result = childProcess.spawnSync(executable, args, {
            encoding: "utf8",
            timeout: 4000,
            windowsHide: true,
        });

        if (result.status !== 0) {
            return "";
        }

        return String(result.stdout || "")
            .split(/\r?\n/)
            .map((line) => line.trim())
            .find(Boolean) || "";
    } catch {
        return "";
    }
}

function shellQuote(value) {
    return `'${String(value).replaceAll("'", `'\\''`)}'`;
}

async function fetchJson(pathname, options = {}) {
    const base = String(getConfig("apiBaseUrl") || "http://127.0.0.1:8000").replace(/\/+$/, "");
    const headers = new Headers(options.headers || {});
    const apiKey = String(getConfig("apiKey") || "").trim();

    if (apiKey && !headers.has("Authorization") && !headers.has("X-Limbi-API-Key")) {
        headers.set("Authorization", `Bearer ${apiKey}`);
    }

    const response = await fetch(`${base}${pathname}`, {
        ...options,
        headers,
    });
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`Limbi API ${response.status}: ${text}`);
    }
    return response.json();
}

function getSelectionContext() {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.selection.isEmpty) {
        return null;
    }

    return {
        filePath: editor.document.uri.fsPath,
        languageId: editor.document.languageId,
        selectedText: editor.document.getText(editor.selection),
        lineStart: editor.selection.start.line + 1,
        lineEnd: editor.selection.end.line + 1,
    };
}

function buildSelectionContextBlock(selection) {
    return [
        "Selected editor context:",
        `File: ${selection.filePath}`,
        `Language: ${selection.languageId}`,
        `Lines: ${selection.lineStart}-${selection.lineEnd}`,
        "",
        "```",
        selection.selectedText,
        "```",
    ].join("\n");
}

function buildSelectionPrompt(selection) {
    return `Please analyze this selected code, explain what it does, identify risks, and suggest the next best action.\n\n${buildSelectionContextBlock(selection)}`;
}

module.exports = {
    activate,
    deactivate,
};
