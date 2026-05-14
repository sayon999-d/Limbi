from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import click
from limbi.llm_provider import list_available_models, provider_requires_api_key


_PROVIDER_CHOICES = {
    "ollama": {
        "model": "llama3.2:3b",
        "base_url": "http://localhost:11434",
        "type": "local",
        "description": "Local models via Ollama",
    },
    "ollama_cloud": {
        "model": "gpt-oss:120b-cloud",
        "base_url": "https://ollama.com/v1",
        "type": "cloud",
        "description": "Ollama Cloud models",
    },
    "openrouter": {
        "model": "openai/gpt-4o",
        "base_url": "https://openrouter.ai/api/v1",
        "type": "remote",
        "description": "OpenRouter model router",
    },
    "huggingface": {
        "model": "meta-llama/Llama-3.1-8B-Instruct",
        "base_url": "https://router.huggingface.co/v1",
        "type": "remote",
        "description": "Hugging Face Inference Providers",
    },
    "chutes": {
        "model": "meta-llama/Llama-3.1-8B-Instruct",
        "base_url": "https://llm.chutes.ai/v1",
        "type": "remote",
        "description": "Chutes open-source model router",
    },
    "bytez": {
        "model": "meta-llama/Llama-3.1-8B-Instruct",
        "base_url": "https://api.bytez.com/models/v2/openai/v1",
        "type": "remote",
        "description": "Bytez unified model API",
    },
    "lmstudio": {
        "model": "default",
        "base_url": "http://localhost:1234/v1",
        "type": "local",
        "description": "Local OpenAI-compatible server via LM Studio",
    },
    "vllm": {
        "model": "default",
        "base_url": "http://localhost:8000/v1",
        "type": "local",
        "description": "Local OpenAI-compatible server via vLLM",
    },
    "localai": {
        "model": "default",
        "base_url": "http://localhost:8080/v1",
        "type": "local",
        "description": "Local OpenAI-compatible server via LocalAI",
    },
    "koboldcpp": {
        "model": "default",
        "base_url": "http://localhost:5001/v1",
        "type": "local",
        "description": "Local OpenAI-compatible server via KoboldCpp",
    },
    "llamacpp": {
        "model": "default",
        "base_url": "http://localhost:8081/v1",
        "type": "local",
        "description": "Local OpenAI-compatible server via llama.cpp",
    },
    "openai_compatible": {
        "model": "default",
        "base_url": "",
        "type": "custom",
        "description": "Any OpenAI-compatible API",
    },
    "openai": {
        "model": "gpt-4o",
        "base_url": "",
        "type": "hosted",
        "description": "OpenAI (GPT-4o, etc.)",
    },
    "anthropic": {
        "model": "claude-sonnet-4-20250514",
        "base_url": "",
        "type": "hosted",
        "description": "Anthropic (Claude)",
    },
    "google": {
        "model": "gemini-1.5-pro",
        "base_url": "",
        "type": "hosted",
        "description": "Google (Gemini)",
    },
    "groq": {
        "model": "llama-3.1-70b-versatile",
        "base_url": "",
        "type": "hosted",
        "description": "Groq (fast inference)",
    },
    "together": {
        "model": "meta-llama/Llama-3-70b-chat-hf",
        "base_url": "",
        "type": "hosted",
        "description": "Together AI",
    },
    "mistral": {
        "model": "mistral-large-latest",
        "base_url": "",
        "type": "hosted",
        "description": "Mistral AI",
    },
    "azure": {
        "model": "gpt-4o",
        "base_url": "",
        "type": "hosted",
        "description": "Azure OpenAI",
    },
    "cohere": {
        "model": "command-r-plus",
        "base_url": "",
        "type": "hosted",
        "description": "Cohere (Command-R)",
    },
}

_LOW_MEMORY_LOCAL_MODELS = {
    "default": [
        "llama3.2:3b",
        "qwen2.5:3b",
        "phi3.5-mini-instruct",
        "gemma2:2b",
    ],
    "ollama": [
        "llama3.2:3b",
        "qwen2.5:3b",
        "phi3.5-mini-instruct",
        "gemma2:2b",
    ],
    "lmstudio": [
        "Llama-3.2-3B-Instruct",
        "Qwen2.5-3B-Instruct",
        "Phi-3.5-mini-instruct",
        "Gemma-2-2B-it",
    ],
    "vllm": [
        "Llama-3.2-3B-Instruct",
        "Qwen2.5-3B-Instruct",
        "Phi-3.5-mini-instruct",
        "Gemma-2-2B-it",
    ],
    "localai": [
        "Llama-3.2-3B-Instruct",
        "Qwen2.5-3B-Instruct",
        "Phi-3.5-mini-instruct",
        "Gemma-2-2B-it",
    ],
    "koboldcpp": [
        "llama3.2:3b",
        "qwen2.5:3b",
        "phi3.5-mini-instruct",
        "gemma2:2b",
    ],
    "llamacpp": [
        "llama3.2:3b",
        "qwen2.5:3b",
        "phi3.5-mini-instruct",
        "gemma2:2b",
    ],
}

_OLLAMA_CLOUD_MODELS = [
    "deepseek-v3.1:671b-cloud",
    "qwen3-coder:480b-cloud",
    "gpt-oss:120b-cloud",
    "gpt-oss:20b-cloud",
    "glm-4.7:cloud",
    "minimax-m2.1:cloud",
]


def _get_console():
    from rich.console import Console

    return Console()


def _print_banner(console):
    from rich.panel import Panel
    from rich.text import Text

    banner = Text()
    banner.append("Limbi", style="bold orange1")
    banner.append(" v1.4.3", style="bold white")
    banner.append(" - Omni-Agent Orchestrator\n")
    banner.append("Type your prompt, or ", style="white")
    banner.append("/models", style="bold orange1")
    banner.append(", ", style="white")
    banner.append("/agent", style="bold orange1")
    banner.append(", or ", style="white")
    banner.append("/agents", style="bold orange1")
    banner.append(" for menus. ", style="white")
    banner.append("/help", style="bold orange1")
    banner.append(" shows the full list. ", style="white")
    banner.append("/quit", style="bold orange1")
    banner.append(" exits.\n", style="white")
    banner.append("Use Up/Down and Enter in selection screens.", style="white")

    console.print(Panel(banner, border_style="orange1", padding=(0, 2)))


def _read_menu_key() -> str:
    if os.name == "nt":
        import msvcrt

        while True:
            key = msvcrt.getwch()
            if key in ("\r", "\n"):
                return "enter"
            if key == "\x03":
                raise KeyboardInterrupt
            if key in ("\x00", "\xe0"):
                code = msvcrt.getwch()
                if code == "H":
                    return "up"
                if code == "P":
                    return "down"
                if code == "K":
                    return "left"
                if code == "M":
                    return "right"
                continue
            if key == "\x1b":
                return "escape"
            return key

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        key = sys.stdin.read(1)
        if key == "\x03":
            raise KeyboardInterrupt
        if key in ("\r", "\n"):
            return "enter"
        if key == "\x1b":
            next_one = sys.stdin.read(1)
            if next_one == "[":
                next_two = sys.stdin.read(1)
                if next_two == "A":
                    return "up"
                if next_two == "B":
                    return "down"
                if next_two == "C":
                    return "right"
                if next_two == "D":
                    return "left"
            return "escape"
        return key
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _render_menu_entry(entry: Any) -> str:
    if isinstance(entry, dict):
        label = str(entry.get("label") or entry.get("name") or entry.get("value") or "")
        details = str(entry.get("details") or entry.get("description") or "").strip()
        return f"{label} - {details}" if details else label
    if isinstance(entry, tuple) and len(entry) >= 2:
        label = str(entry[0])
        details = str(entry[1]).strip()
        return f"{label} - {details}" if details else label
    return str(entry)


def _select_from_menu(console, title: str, choices: list[Any], default_index: int = 0, help_text: str = "") -> Any:
    if not choices:
        raise click.ClickException(f"No choices available for {title}.")

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        console.print(f"[bold]{title}[/]")
        for idx, choice in enumerate(choices, start=1):
            console.print(f"  {idx}. {_render_menu_entry(choice)}")
        selected = click.prompt(
            "Choose number",
            type=click.IntRange(1, len(choices)),
            default=max(1, min(len(choices), default_index + 1)),
        )
        return choices[selected - 1]

    index = max(0, min(default_index, len(choices) - 1))
    while True:
        console.clear()
        console.print(f"[bold bright_cyan]{title}[/]")
        if help_text:
            console.print(f"[dim]{help_text}[/]")
        console.print()
        for idx, choice in enumerate(choices):
            marker = ">" if idx == index else " "
            style = "bold bright_green" if idx == index else "white"
            console.print(f"[{style}]{marker} {_render_menu_entry(choice)}[/]")

        key = _read_menu_key()
        if key == "up":
            index = (index - 1) % len(choices)
            continue
        if key == "down":
            index = (index + 1) % len(choices)
            continue
        if key in ("enter", "right"):
            return choices[index]
        if key in ("q", "escape"):
            raise click.ClickException("Selection cancelled.")


def _print_agent_table(console):
    from rich.table import Table

    from limbi.agents import list_agents

    agents = list_agents()
    table = Table(
        title="Registered Agents",
        title_style="bold orange1",
        border_style="orange1",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Agent", style="bold white", min_width=25)
    table.add_column("Actions", style="orange1")
    table.add_column("#", justify="right", style="white")

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

    table = Table(
        title="Supported Providers",
        border_style="orange1",
        show_lines=False,
    )
    table.add_column("Provider", style="bold white")
    table.add_column("Description", style="dim")
    table.add_column("Type", style="dim")
    for name, meta in _PROVIDER_CHOICES.items():
        table.add_row(name, meta["description"], meta["type"])
    console.print(table)
    console.print(
        "\n[dim]Set via:[/] [bold]LLM_PROVIDER[/]=provider "
        "[bold]LLM_API_KEY[/]=key [bold]LLM_MODEL[/]=model\n"
    )


def _print_model_choices(console):
    from rich.table import Table

    table = Table(
        title="Model / Provider Choices",
        border_style="orange1",
        show_lines=False,
    )
    table.add_column("Provider", style="bold white")
    table.add_column("Default Model", style="orange1")
    table.add_column("Endpoint", style="dim")
    table.add_column("Key", style="dim")
    for provider, meta in _PROVIDER_CHOICES.items():
        endpoint = meta["base_url"] or "(provider default)"
        if meta["type"] == "custom":
            key_state = "conditional"
        else:
            key_state = "required" if provider_requires_api_key(provider, meta["base_url"]) else "not required"
        table.add_row(provider, meta["model"], endpoint, key_state)
    console.print(table)


def _provider_choice_items() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for name, meta in _PROVIDER_CHOICES.items():
        details = f"{meta['description']} ({meta['type']})"
        if meta["base_url"]:
            details += f" | {meta['base_url']}"
        items.append({"name": name, "label": name, "details": details})
    return items


def _resolve_model_choice(choice: str) -> str:
    normalized = choice.strip().lower().replace(" ", "_")
    if normalized in _PROVIDER_CHOICES:
        return normalized
    alias_map = {
        "claude": "anthropic",
        "gemini": "google",
        "azure_openai": "azure",
        "ollama cloud": "ollama_cloud",
        "ollama-cloud": "ollama_cloud",
        "openai-compatible": "openai_compatible",
        "openai compatible": "openai_compatible",
    }
    return alias_map.get(normalized, normalized)


def _refresh_orchestrator(state: dict[str, Any]) -> None:
    from limbi.orchestrator import Orchestrator

    state["orchestrator"] = Orchestrator()


def _configure_runtime_from_model_choice(state: dict[str, Any], console) -> None:
    from limbi.workspace import save_config

    _print_model_choices(console)
    provider_default = _resolve_model_choice(state.get("provider") or "ollama")
    provider_item = _select_from_menu(
        console,
        "Choose provider",
        _provider_choice_items(),
        default_index=list(_PROVIDER_CHOICES).index(provider_default) if provider_default in _PROVIDER_CHOICES else 0,
        help_text="Use Up/Down to move, then Enter to choose.",
    )
    provider = provider_item["name"]
    defaults = _PROVIDER_CHOICES.get(provider, {})
    base_url = click.prompt(
        "Choose base URL",
        default=defaults.get("base_url") or state.get("base_url") or "",
        show_default=bool(defaults.get("base_url") or state.get("base_url")),
        type=str,
    ).strip()
    api_key = state.get("api_key") or ""
    if provider_requires_api_key(provider, base_url) and not api_key:
        api_key = click.prompt(
            f"Enter API key for {provider}",
            hide_input=True,
            confirmation_prompt=False,
            type=str,
        ).strip()
        if not api_key:
            raise click.ClickException("API key is required for the selected provider.")
    if not provider_requires_api_key(provider, base_url):
        api_key = ""

    catalog_models = list_available_models(provider, api_key=api_key, base_url=base_url)
    if catalog_models:
        preferred_model = state.get("model") if state.get("model") in catalog_models else defaults.get("model")
        if preferred_model not in catalog_models:
            preferred_model = catalog_models[0]
        model_item = _select_from_menu(
            console,
            f"Choose model for {provider}",
            [{"name": item, "label": item, "details": ""} for item in catalog_models],
            default_index=catalog_models.index(preferred_model) if preferred_model in catalog_models else 0,
            help_text="Use Up/Down to move, then Enter to choose.",
        )
        model = model_item["name"]
    elif provider == "ollama_cloud":
        model_item = _select_from_menu(
            console,
            "Choose an Ollama Cloud model",
            [
                {"name": item, "label": item, "details": "hosted by Ollama Cloud; larger models are listed first"}
                for item in _OLLAMA_CLOUD_MODELS
            ],
            default_index=0,
            help_text="These cloud models run on Ollama's hosted service and need an API key. Bigger models usually give stronger answers.",
        )
        model = model_item["name"]
    elif defaults.get("type") == "local":
        suggestions = _LOW_MEMORY_LOCAL_MODELS.get(provider, _LOW_MEMORY_LOCAL_MODELS["default"])
        model_item = _select_from_menu(
            console,
            f"Choose a low-memory model for {provider}",
            [
                {"name": item, "label": item, "details": "recommended for laptops with 16GB RAM"}
                for item in suggestions
            ]
            + [{"name": "__custom__", "label": "Custom model name", "details": "type your own model id"}],
            default_index=0,
            help_text="These are small local models that keep Limbi fast on modest hardware.",
        )
        if model_item["name"] == "__custom__":
            model = click.prompt(
                "Choose model",
                default=defaults.get("model") or state.get("model") or suggestions[0],
                type=str,
            ).strip()
        else:
            model = model_item["name"]
    else:
        model = click.prompt(
            "Choose model",
            default=defaults.get("model") or state.get("model") or "llama3.2:3b",
            type=str,
        ).strip()

    _setup_env_overrides(provider, model, api_key, base_url)
    if not os.environ.get("LLM_MAX_TOKENS"):
        os.environ["LLM_MAX_TOKENS"] = str(min(int(state["ws_config"].get("max_tokens", 1024)), 1024))

    state["provider"] = provider
    state["model"] = model
    state["base_url"] = base_url
    state["api_key"] = api_key
    _refresh_orchestrator(state)

    if click.confirm("Save this provider/model to the workspace config?", default=True):
        ws_config = dict(state["ws_config"])
        ws_config["provider"] = provider
        ws_config["model"] = model
        ws_config["base_url"] = base_url
        ws_config["api_key_set"] = bool(api_key)
        save_config(ws_config)
        state["ws_config"] = ws_config

    provider_summary = state["orchestrator"]._provider  # noqa: SLF001
    console.print(
        f"[green]Provider set:[/] [bold]{provider_summary.provider_name()}[/] "
        f"[green]Model:[/] [bold]{provider_summary.config.model}[/] "
        f"[green]Endpoint:[/] [bold]{provider_summary.config.base_url or '(provider default)'}[/]\n"
    )


def _parse_json_params(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Invalid JSON parameters: {exc}") from exc
    if not isinstance(payload, dict):
        raise click.ClickException("Parameters must be a JSON object.")
    return payload


def _run_manual_agent(console) -> None:
    from limbi.agents import get_agent, list_agents
    from rich.panel import Panel
    from rich.syntax import Syntax

    agents = list_agents()
    if not agents:
        console.print("[yellow]No agents are registered.[/]")
        return

    agent_item = _select_from_menu(
        console,
        "Choose agent",
        [{"name": name, "label": name, "details": f"{len(actions)} actions"} for name, actions in sorted(agents.items())],
        help_text="Use Up/Down to move, then Enter to choose.",
    )
    agent_name = agent_item["name"]

    agent = get_agent(agent_name)
    actions = agent.available_actions
    action_item = _select_from_menu(
        console,
        f"Choose action for {agent_name}",
        [{"name": action, "label": action, "details": ""} for action in actions],
        help_text="Use Up/Down to move, then Enter to choose.",
    )
    action = action_item["name"]

    params_raw = click.prompt(
        "Enter JSON parameters",
        default="{}",
        show_default=False,
        type=str,
    )
    params = _parse_json_params(params_raw)
    result = agent.execute(action, params)

    console.print(
        Panel(
            Syntax(json.dumps(result.to_dict(), indent=2), "json", word_wrap=True),
            title=f"{agent_name}.{action}",
            border_style="orange1" if result.success else "red",
            padding=(1, 2),
        )
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


def _setup_env_overrides(
    provider: str | None,
    model: str | None,
    api_key: str | None,
    base_url: str | None = None,
):
    if provider:
        os.environ["LLM_PROVIDER"] = provider
    if model:
        os.environ["LLM_MODEL"] = model
    if base_url is not None:
        if base_url:
            os.environ["LLM_BASE_URL"] = base_url
        else:
            os.environ.pop("LLM_BASE_URL", None)
    if api_key is not None:
        if api_key:
            os.environ["LLM_API_KEY"] = api_key
        else:
            os.environ.pop("LLM_API_KEY", None)


def _ensure_api_key(provider: str | None, api_key: str | None, base_url: str | None = None) -> str | None:
    resolved_provider = (provider or os.environ.get("LLM_PROVIDER", "ollama")).strip().lower()
    resolved_base_url = (base_url or os.environ.get("LLM_BASE_URL", "")).strip()
    resolved_key = (api_key or os.environ.get("LLM_API_KEY", "")).strip()

    if not provider_requires_api_key(resolved_provider, resolved_base_url):
        return resolved_key or None

    if resolved_key:
        return resolved_key

    if not sys.stdin.isatty():
        raise click.ClickException(
        f"Provider '{resolved_provider}' requires an API key, but the terminal is not interactive."
        )

    entered = click.prompt(
        f"Enter API key for {resolved_provider}",
        hide_input=True,
        confirmation_prompt=False,
        type=str,
    ).strip()
    if not entered:
        raise click.ClickException("API key is required for the selected provider.")

    return entered


def _is_parser_noise(error: str) -> bool:
    return error.startswith(
        (
            "JSONDecodeError:",
            "Unexpected JSON type:",
            "Validation error:",
        )
    )


async def _status_ticker(status, stop_event: asyncio.Event) -> None:
    started = time.perf_counter()
    while not stop_event.is_set():
        elapsed = time.perf_counter() - started
        status.update(f"[bold orange1]Thinking... {elapsed:.1f}s[/]")
        try:
            await asyncio.sleep(0.8)
        except asyncio.CancelledError:
            return


async def _send_message(orchestrator, message: str, console) -> None:
    from rich.markdown import Markdown
    from rich.panel import Panel

    stop_event = asyncio.Event()
    with console.status("[bold orange1]Thinking...[/]", spinner="dots") as status:
        ticker = asyncio.create_task(_status_ticker(status, stop_event))
        try:
            result = await orchestrator.chat(message)
        finally:
            stop_event.set()
            ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ticker

    text = result.get("conversation_text", "").strip()
    delegations = result.get("delegations_executed", [])
    errors = result.get("errors", [])
    metrics = result.get("metrics", {})

    if text:
        console.print(
            Panel(
                Markdown(text),
                title="[bold orange1]Limbi[/]",
                border_style="orange1",
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

    if metrics:
        from rich.text import Text

        summary = Text()
        summary.append("hallucination: ", style="bold orange1")
        summary.append(f"{metrics.get('estimated_hallucination_risk_percent', 0)}%", style="white")
        summary.append("    ", style="white")
        summary.append("latency: ", style="bold orange1")
        summary.append(f"{metrics.get('latency_s', 0):.2f}s", style="white")
        summary.append("    ", style="white")
        summary.append("token usage: ", style="bold orange1")
        summary.append(str(metrics.get('total_tokens', 0)), style="white")
        console.print(Panel(summary, border_style="orange1", padding=(0, 1)))


def _repl(state, console):
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

        orchestrator = state["orchestrator"]

        if user_input.startswith("/"):
            cmd = user_input.lower().split()[0]
            if cmd in ("/quit", "/exit", "/q"):
                console.print("Goodbye.")
                break
            if cmd in ("/agent",):
                _run_manual_agent(console)
                continue
            if cmd in ("/agents",):
                _run_manual_agent(console)
                continue
            if cmd in ("/list",):
                _print_agent_table(console)
                continue
            if cmd in ("/model",):
                _configure_runtime_from_model_choice(state, console)
                continue
            if cmd in ("/providers",):
                _print_providers(console)
                continue
            if cmd in ("/models",):
                _configure_runtime_from_model_choice(state, console)
                continue
            if cmd in ("/clear",):
                orchestrator.clear_history()
                console.print("History cleared.")
                continue
            if cmd in ("/trust",):
                from limbi.workspace_trust import get_trust_level, list_trusted_workspaces
                level = get_trust_level()
                if level:
                    style = "green" if level == "full" else "cyan" if level == "readonly" else "red"
                    console.print(f"  Workspace trust: [{style}]{level}[/]")
                else:
                    console.print("  Workspace trust: [yellow]not set[/]")
                trusted = list_trusted_workspaces()
                if trusted:
                    console.print(f"  [dim]Trusted workspaces: {len(trusted)}[/]")
                console.print()
                continue
            if cmd in ("/help", "/h"):
                console.print(
                    Markdown(
                        """## Commands
| Command | Description |
|---------|-------------|
| `/agents` | Manually choose an agent and run one action |
| `/agent` | Alias for `/agents` |
| `/model` | Alias for `/models` |
| `/providers` | Show supported LLM providers |
| `/models` | Choose provider, model, and API key for the session |
| `/list` | List all registered agents |
| `/trust` | Show workspace trust status |
| `/clear` | Clear conversation history |
| `/help` | Show this help |
| `/quit` | Exit Limbi |

Type a natural-language prompt to talk to Limbi.

**CLI Flags:** `--trust-reset` (re-prompt trust) · `--skip-trust` (CI mode)
"""
                    )
                )
                continue

        asyncio.run(_send_message(state["orchestrator"], user_input, console))


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("prompt", required=False, default=None)
@click.option(
    "--provider",
    "-p",
    envvar="LLM_PROVIDER",
    default=None,
    help=(
        "LLM provider (ollama, lmstudio, vllm, localai, koboldcpp, llamacpp, "
        "openrouter, huggingface, chutes, bytez, openai, anthropic, google, "
        "groq, together, mistral, azure, cohere)."
    ),
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
@click.option(
    "--trust-reset",
    is_flag=True,
    default=False,
    help="Reset workspace trust and re-prompt.",
)
@click.option(
    "--skip-trust",
    is_flag=True,
    default=False,
    help="Skip workspace trust prompt (for CI/automation).",
)
@click.version_option(version="1.4.3", prog_name="limbi")
def main(
    prompt: str | None,
    provider: str | None,
    model: str | None,
    api_key: str | None,
    list_agents: bool,
    list_providers: bool,
    generate_mcp_config: bool,
    mcp_config_path: str | None,
    trust_reset: bool,
    skip_trust: bool,
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

    from limbi.workspace_trust import (
        check_workspace_trust,
        revoke_workspace_trust,
        list_trusted_workspaces,
    )

    if trust_reset:
        revoke_workspace_trust()
        console.print("[yellow]Workspace trust reset.[/] You will be prompted again.\n")

    if not skip_trust and not os.environ.get("LIMBI_SKIP_TRUST"):
        trust_level = check_workspace_trust(console=console)
        if trust_level == "denied":
            sys.exit(1)
    else:
        trust_level = "full"

    from limbi.workspace import init_workspace, load_config, save_config

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
    if not os.environ.get("LLM_BASE_URL"):
        os.environ["LLM_BASE_URL"] = ws_config.get("base_url", "")

    api_key = _ensure_api_key(provider, api_key, os.environ.get("LLM_BASE_URL"))
    _setup_env_overrides(provider, model, api_key, os.environ.get("LLM_BASE_URL"))

    if provider_requires_api_key(
        (provider or os.environ.get("LLM_PROVIDER", "ollama")).strip().lower(),
        os.environ.get("LLM_BASE_URL"),
    ):
        if not os.environ.get("LLM_MAX_TOKENS"):
            workspace_max_tokens = int(ws_config.get("max_tokens", 1024))
            os.environ["LLM_MAX_TOKENS"] = str(min(workspace_max_tokens, 1024))

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
    state = {
        "orchestrator": orchestrator,
        "provider": provider_obj.provider_name(),
        "model": provider_obj.config.model,
        "base_url": provider_obj.config.base_url,
        "api_key": provider_obj.config.api_key,
        "ws_config": ws_config,
        "save_config": save_config,
    }
    console.print(
        f"[dim]Provider:[/] [bold]{provider_obj.provider_name()}[/] "
        f"[dim]Model:[/] [bold]{provider_obj.config.model}[/] "
        f"[dim]Agents:[/] [bold]{len(_limbi.list_agents())}[/]"
        f"[dim] Workspace:[/] [bold]{ws_result['workspace']}[/]\n"
    )

    if prompt:
        asyncio.run(_send_message(state["orchestrator"], prompt, console))
    else:
        _repl(state, console)


if __name__ == "__main__":
    main()
