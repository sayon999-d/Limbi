
This extension connects VS Code to the Limbi backend running from this repository.

- sidebar chat with the Limbi API
- agent inventory pulled from `/api/agents`
- selection-aware prompts from the active editor
- MCP config generation for editor agents that support MCP

Recommended terminal setup:

```bash
python -m limbi --generate-mcp-config
```

That writes `.vscode/mcp.json` using the packaged MCP server:

```bash
python -m limbi.mcp_server
```

VS Code extension development setup:

1. Start the Limbi API from the repository root:

```bash
uvicorn main:app --reload
```

2. Open the `limbi-vscode` folder in VS Code.
3. Press `F5` and choose **Run Limbi Extension** to launch the Extension Development Host.

In the Extension Development Host, open the VS Code Command Palette with
`Cmd+Shift+P` on macOS or `Ctrl+Shift+P` on Windows/Linux, then run:

`Limbi: Generate MCP Config`

This is a VS Code command-palette command, not a terminal command. Do not run
`Limbi: Generate MCP Config` or `limbi: Generate MCP Config` in zsh/bash.
Also make sure the command starts with `Limbi:`. Commands such as
`React Native: Create EAS config file for Expo` come from other VS Code
extensions and are unrelated to Limbi.

If no `Limbi:` commands appear in the Command Palette, the extension is not
running yet. Return to the VS Code window opened on `limbi-vscode`, press `F5`,
and start the **Run Limbi Extension** launch configuration.

That writes `.vscode/mcp.json` in the workspace pointing to `python -m limbi.mcp_server`.
By default, the extension resolves `limbi.pythonCommand` through your login shell first so PATH-managed interpreters from tools like pyenv, Homebrew, or virtual environments are more likely to work in MCP clients.
