(function () {
    const vscode = acquireVsCodeApi();

    const statusText = document.getElementById("status-text");
    const statusSubtext = document.getElementById("status-subtext");
    const promptInput = document.getElementById("prompt-input");
    const sendBtn = document.getElementById("send-btn");
    const refreshBtn = document.getElementById("refresh-btn");
    const clearBtn = document.getElementById("clear-btn");
    const selectionBtn = document.getElementById("selection-btn");
    const messages = document.getElementById("messages");
    const agentsList = document.getElementById("agents-list");

    sendBtn.addEventListener("click", () => {
        vscode.postMessage({ type: "sendPrompt", prompt: promptInput.value });
    });

    refreshBtn.addEventListener("click", () => {
        vscode.postMessage({ type: "refresh" });
    });

    clearBtn.addEventListener("click", () => {
        vscode.postMessage({ type: "clearChat" });
    });

    selectionBtn.addEventListener("click", () => {
        vscode.postMessage({ type: "selectionPrompt" });
    });

    promptInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
            event.preventDefault();
            sendBtn.click();
        }
    });

    window.addEventListener("message", (event) => {
        const message = event.data;
        switch (message.type) {
            case "state":
                renderHealth(message.health || {});
                renderAgents(message.agents || {});
                break;
            case "chatPending":
                appendMessage("user", message.prompt || "");
                appendMessage("assistant", "Limbi is working...");
                promptInput.value = "";
                break;
            case "chatResult":
                replaceLastAssistant(message.response?.conversation_text || "(no response)");
                break;
            case "error":
                appendMessage("assistant", `Error: ${message.error}`);
                break;
            case "draftPrompt":
                promptInput.value = message.prompt || "";
                promptInput.focus();
                break;
            case "chatCleared":
                messages.innerHTML = "";
                appendMessage("assistant", "Conversation history cleared in the Limbi backend.");
                break;
        }
    });

    function renderHealth(health) {
        if (health.error) {
            statusText.textContent = "Offline";
            statusSubtext.textContent = health.error;
            return;
        }

        statusText.textContent = `${health.status || "unknown"} - ${health.agents_registered || 0} agents`;
        const provider = health.llm_provider?.provider || "unknown";
        const model = health.llm_provider?.model || "unknown";
        statusSubtext.textContent = `${provider} - ${model}`;
    }

    function renderAgents(payload) {
        const agents = payload.agents || {};
        const names = Object.keys(agents).sort();
        if (!names.length) {
            agentsList.innerHTML = "<div class='agent-card'>No agents registered.</div>";
            return;
        }

        agentsList.innerHTML = names.map((name) => {
            const actions = agents[name]?.actions || [];
            return `
                <details class="agent-card">
                  <summary>
                    <span>${escapeHtml(name)}</span>
                    <span class="action-count">${actions.length} actions</span>
                  </summary>
                  <div class="action-list">${actions.map((action) => `<code>${escapeHtml(action)}</code>`).join("")}</div>
                </details>
            `;
        }).join("");
    }

    function appendMessage(role, text) {
        const item = document.createElement("div");
        item.className = `message ${role}`;
        item.innerHTML = `
            <div class="message-role">${role === "user" ? "You" : "Limbi"}</div>
            <pre class="message-body">${escapeHtml(text)}</pre>
        `;
        messages.appendChild(item);
        messages.scrollTop = messages.scrollHeight;
    }

    function replaceLastAssistant(text) {
        const assistants = Array.from(messages.querySelectorAll(".message.assistant"));
        const last = assistants.at(-1);
        if (!last) {
            appendMessage("assistant", text);
            return;
        }
        const body = last.querySelector(".message-body");
        body.textContent = text;
        messages.scrollTop = messages.scrollHeight;
    }

    function escapeHtml(value) {
        return String(value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;");
    }

    vscode.postMessage({ type: "ready" });
})();
