from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import click


def _get_console():
    from rich.console import Console

    return Console()


def _print_banner(console):
    from rich.panel import Panel
    from rich.text import Text

    banner = Text()
    banner.append("Limbi", style="bold bright_cyan")
    banner.append(" v1.0.2", style="dim")
    banner.append(" - Omni-Agent Orchestrator\n")
    banner.append("Type your prompt, or ", style="dim")
    banner.append("/help", style="bold green")
    banner.append(" for commands. ", style="dim")
    banner.append("/quit", style="bold red")
    banner.append(" to exit.", style="dim")

    console.print(Panel(banner, border_style="bright_cyan", padding=(0, 2)))


def _print_agent_table(console):
    from rich.table import Table

    from limbi.agents import list_agents

    agents = list_agents()
    table = Table(
        title="Registered Agents",
        title_style="bold bright_cyan",
        border_style="bright_cyan",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Agent", style="bold white", min_width=25)
    table.add_column("Actions", style="cyan")
    table.add_column("#", justify="right", style="green")

    for name, actions in sorted(agents.items()):
        table.add_row(
            name,
            ", ".join(actions[:5]) + ("..." if len(actions) > 5 else ""),
            str(len(actions)),
        )

    console.print(table)
    console.print(
        f"\n[dim]Total:[/] [bold green]{len(agents)}[/] agents, "
        f"[bold green]{sum(len(a) for a in agents.values())}[/] actions\n"
    )


def _print_providers(console):
    from rich.table import Table

    providers = {
        "ollama": "Local models via Ollama",
        "openai": "OpenAI (GPT-4o, etc.)",
        "anthropic": "Anthropic (Claude)",
        "google": "Google (Gemini)",
        "groq": "Groq (fast inference)",
        "together": "Together AI",
        "mistral": "Mistral AI",
        "azure": "Azure OpenAI",
        "cohere": "Cohere (Command-R)",
        "openai_compatible": "Any OpenAI-compatible API",
    }
    table = Table(
        title="Supported Providers",
        border_style="bright_cyan",
        show_lines=False,
    )
    table.add_column("Provider", style="bold white")
    table.add_column("Description", style="dim")
    for name, desc in providers.items():
        table.add_row(name, desc)
    console.print(table)
    console.print(
        "\n[dim]Set via:[/] [bold]LLM_PROVIDER[/]=provider "
        "[bold]LLM_API_KEY[/]=key [bold]LLM_MODEL[/]=model\n"
    )


def _generate_mcp_config(config_path: str | None = None) -> Path:
    path = Path(config_path or ".vscode/mcp.json").expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)

    config = {
        "servers": {
            "limbi": {
                "type": "stdio",
                "command": sys.executable,
                "args": ["-m", "limbi.mcp_server"],
            }
        }
    }
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return path


def _setup_env_overrides(provider: str | None, model: str | None, api_key: str | None):
    if provider:
        os.environ["LLM_PROVIDER"] = provider
    if model:
        os.environ["LLM_MODEL"] = model
    if api_key:
        os.environ["LLM_API_KEY"] = api_key


def _is_parser_noise(error: str) -> bool:
    return error.startswith(
        (
            "JSONDecodeError:",
            "Unexpected JSON type:",
            "Validation error:",
        )
    )


async def _send_message(orchestrator, message: str, console) -> None:
    from rich.markdown import Markdown
    from rich.panel import Panel

    with console.status("[bold cyan]Thinking...[/]", spinner="dots"):
        result = await orchestrator.chat(message)

    text = result.get("conversation_text", "").strip()
    delegations = result.get("delegations_executed", [])
    errors = result.get("errors", [])

    if text:
        console.print(
            Panel(
                Markdown(text),
                title="[bold bright_cyan]Limbi[/]",
                border_style="bright_cyan",
                padding=(1, 2),
            )
        )

    if delegations:
        for d in delegations:
            status = "OK" if d.get("success") else "FAIL"
            agent = d.get("agent", "?")
            action = d.get("action", "?")
            msg = d.get("data", {}).get("message", d.get("error", ""))
            console.print(f"  {status} [bold]{agent}[/].[cyan]{action}[/] -> {msg}")
        console.print()

    visible_errors = [e for e in errors if not _is_parser_noise(e)]
    if visible_errors:
        for e in visible_errors:
            console.print(f"  [red]WARNING: {e}[/]")
    elif errors and not text and not delegations:
        console.print("  [yellow]WARNING: Could not fully parse the model response.[/]")


def _repl(orchestrator, console):
    from rich.markdown import Markdown

    _print_banner(console)

    while True:
        try:
            user_input = console.input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye.")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            cmd = user_input.lower().split()[0]
            if cmd in ("/quit", "/exit", "/q"):
                console.print("Goodbye.")
                break
            if cmd in ("/agents", "/list"):
                _print_agent_table(console)
                continue
            if cmd in ("/providers",):
                _print_providers(console)
                continue
            if cmd in ("/clear",):
                orchestrator.clear_history()
                console.print("History cleared.")
                continue
            if cmd in ("/help", "/h"):
                console.print(
                    Markdown(
                        """## Commands
| Command | Description |
|---------|-------------|
| `/agents` | List all registered agents |
| `/providers` | Show supported LLM providers |
| `/clear` | Clear conversation history |
| `/help` | Show this help |
| `/quit` | Exit Limbi |

Type a natural-language prompt to talk to Limbi.
"""
                    )
                )
                continue

        asyncio.run(_send_message(orchestrator, user_input, console))


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("prompt", required=False, default=None)
@click.option(
    "--provider",
    "-p",
    envvar="LLM_PROVIDER",
    default=None,
    help="LLM provider (ollama, openai, anthropic, google, groq, together, mistral, azure, cohere).",
)
@click.option(
    "--model",
    "-m",
    envvar="LLM_MODEL",
    default=None,
    help="Model name (e.g. gpt-4o, claude-sonnet-4-20250514, llama3.2:3b).",
)
@click.option(
    "--api-key",
    "-k",
    envvar="LLM_API_KEY",
    default=None,
    help="API key for the provider (or set LLM_API_KEY env var).",
)
@click.option(
    "--list-agents",
    "-l",
    is_flag=True,
    default=False,
    help="List all registered agents and exit.",
)
@click.option(
    "--list-providers",
    is_flag=True,
    default=False,
    help="List supported LLM providers and exit.",
)
@click.option(
    "--generate-mcp-config",
    is_flag=True,
    default=False,
    help="Write .vscode/mcp.json for the packaged Limbi MCP server and exit.",
)
@click.option(
    "--mcp-config-path",
    default=None,
    help="Path for --generate-mcp-config (default: .vscode/mcp.json).",
)
@click.version_option(version="1.0.2", prog_name="limbi")
def main(
    prompt: str | None,
    provider: str | None,
    model: str | None,
    api_key: str | None,
    list_agents: bool,
    list_providers: bool,
    generate_mcp_config: bool,
    mcp_config_path: str | None,
):
    console = _get_console()

    if generate_mcp_config:
        config_path = _generate_mcp_config(mcp_config_path)
        console.print(f"[green]Limbi MCP config written:[/] [bold]{config_path}[/]")
        console.print(
            "[dim]Server command:[/] "
            f"[bold]{sys.executable} -m limbi.mcp_server[/]"
        )
        return

    from limbi.workspace import init_workspace, load_config

    ws_result = init_workspace()

    if ws_result["is_new"]:
        from rich.panel import Panel
        from rich.text import Text

        welcome = Text()
        welcome.append("Limbi workspace initialized!\n\n", style="bold bright_cyan")
        welcome.append(f"  Workspace:           {ws_result['workspace']}\n", style="")
        welcome.append("  config.json          ", style="dim")
        welcome.append("provider settings\n", style="dim italic")
        welcome.append("  audit.db             ", style="dim")
        welcome.append("execution log\n", style="dim italic")
        welcome.append("  memory.db            ", style="dim")
        welcome.append("conversation memory\n", style="dim italic")
        welcome.append("  context_memory.db    ", style="dim")
        welcome.append("inter-agent shared context\n", style="dim italic")
        welcome.append("  chroma_db/           ", style="dim")
        welcome.append("vector store (RAG)\n\n", style="dim italic")
        welcome.append("  Edit ", style="dim")
        welcome.append(".limbi/config.json", style="bold")
        welcome.append(" to change defaults.", style="dim")

        console.print(Panel(welcome, border_style="green", padding=(1, 2)))
        console.print()

    if list_agents:
        import limbi

        _print_agent_table(console)
        return

    if list_providers:
        _print_providers(console)
        return

    ws_config = load_config()

    if not provider and not os.environ.get("LLM_PROVIDER"):
        provider = ws_config.get("provider")
    if not model and not os.environ.get("LLM_MODEL"):
        model = ws_config.get("model")

    _setup_env_overrides(provider, model, api_key)

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    import limbi as _limbi
    from limbi.orchestrator import Orchestrator
    from limbi.audit_log import init_db

    init_db()
    orchestrator = Orchestrator()

    provider_obj = _limbi.get_llm_provider()
    console.print(
        f"[dim]Provider:[/] [bold]{provider_obj.provider_name()}[/] "
        f"[dim]Model:[/] [bold]{provider_obj.config.model}[/] "
        f"[dim]Agents:[/] [bold]{len(_limbi.list_agents())}[/]"
        f"[dim] Workspace:[/] [bold].limbi/[/]\n"
    )

    if prompt:
        asyncio.run(_send_message(orchestrator, prompt, console))
    else:
        _repl(orchestrator, console)


if __name__ == "__main__":
    main()
