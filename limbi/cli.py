from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

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

_MISSING = object()


def _get_console():
    from rich.console import Console

    return Console()


def _print_banner(console):
    from rich.panel import Panel
    from rich.text import Text

    banner = Text()
    banner.append("Limbi", style="bold orange1")
    banner.append(" v1.6.1", style="bold white")
    banner.append(" - Omni-Agent Orchestrator\n")
    banner.append("Type your prompt, or ", style="white")
    banner.append("/models", style="bold orange1")
    banner.append(", ", style="white")
    banner.append("/skills", style="bold orange1")
    banner.append(", ", style="white")
    banner.append("/agent", style="bold orange1")
    banner.append(", or ", style="white")
    banner.append("/agents", style="bold orange1")
    banner.append(", ", style="white")
    banner.append("/keys", style="bold orange1")
    banner.append(", ", style="white")
    banner.append("/help", style="bold orange1")
    banner.append(" or ", style="white")
    banner.append("/quit", style="bold orange1")
    banner.append(".\n", style="white")
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


def _provider_base_url(provider: str, state: dict[str, Any] | None = None) -> str:
    defaults = _PROVIDER_CHOICES.get(provider, {})
    if state and state.get("base_url"):
        return str(state["base_url"]).strip()
    return str(defaults.get("base_url") or "").strip()


def _store_provider_api_key(
    state: dict[str, Any],
    provider: str,
    api_key: str,
    base_url: str,
) -> None:
    from limbi.workspace import save_config, set_provider_api_key

    ws_config = dict(state["ws_config"])
    ws_config = set_provider_api_key(ws_config, provider, api_key, base_url)
    save_config(ws_config)
    state["ws_config"] = ws_config
    if state.get("provider") == provider and str(state.get("base_url") or "").strip() == base_url:
        state["api_key"] = api_key
        _setup_env_overrides(provider, state.get("model"), api_key, base_url)
        _refresh_orchestrator(state)


def _delete_provider_api_key(
    state: dict[str, Any],
    provider: str,
    base_url: str,
) -> None:
    from limbi.workspace import delete_provider_api_key, save_config

    ws_config = dict(state["ws_config"])
    ws_config = delete_provider_api_key(ws_config, provider, base_url)
    save_config(ws_config)
    state["ws_config"] = ws_config
    if state.get("provider") == provider and str(state.get("base_url") or "").strip() == base_url:
        state["api_key"] = ""
        _setup_env_overrides(provider, state.get("model"), None, base_url)
        _refresh_orchestrator(state)


def _ensure_runtime_api_key(state: dict[str, Any], console) -> str | None:
    from limbi.workspace import get_provider_api_key

    provider = str(state.get("provider") or os.environ.get("LLM_PROVIDER", "ollama")).strip().lower()
    base_url = str(state.get("base_url") or os.environ.get("LLM_BASE_URL", "")).strip()
    if not provider_requires_api_key(provider, base_url):
        return None

    saved_key = str(state.get("api_key") or "").strip()
    if not saved_key:
        saved_key = str(os.environ.get("LLM_API_KEY", "")).strip()
    if not saved_key:
        saved_key = get_provider_api_key(state["ws_config"], provider, base_url)

    if saved_key:
        _store_provider_api_key(state, provider, saved_key, base_url)
        return saved_key

    if not sys.stdin.isatty():
        raise click.ClickException(
            f"Provider '{provider}' requires an API key. Run /models or /keys to save one first."
        )

    api_key = click.prompt(
        f"Enter API key for {provider}",
        hide_input=True,
        confirmation_prompt=False,
        type=str,
    ).strip()
    if not api_key:
        raise click.ClickException("API key is required for the selected provider.")

    _store_provider_api_key(state, provider, api_key, base_url)
    return api_key


def _refresh_orchestrator(state: dict[str, Any]) -> None:
    from limbi.orchestrator import Orchestrator

    state["orchestrator"] = Orchestrator(session_id=state.get("session_id", "global"))
    try:
        state["orchestrator"]._sync_session_state()  # noqa: SLF001
    except Exception:
        pass


def _configure_runtime_from_model_choice(state: dict[str, Any], console) -> None:
    from limbi.workspace import get_provider_api_key, save_config, set_provider_api_key

    ws_config = state["ws_config"]

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
    base_url = str(defaults.get("base_url") or "").strip()
    if state.get("provider") == provider and state.get("base_url"):
        base_url = str(state.get("base_url") or "").strip()
    if provider == "openai_compatible":
        base_url = click.prompt(
            "Choose base URL",
            default=base_url,
            show_default=bool(base_url),
            type=str,
        ).strip()

    api_key = ""
    if state.get("provider") == provider and str(state.get("base_url") or "").strip() == base_url:
        api_key = str(state.get("api_key") or "").strip()
    if not api_key:
        api_key = get_provider_api_key(ws_config, provider, base_url)
    if provider_requires_api_key(provider, base_url) and not api_key:
        api_key = click.prompt(
            f"Enter API key for {provider}",
            hide_input=True,
            confirmation_prompt=False,
            type=str,
        ).strip()
        if not api_key:
            raise click.ClickException("API key is required for the selected provider.")
    if provider_requires_api_key(provider, base_url) and api_key:
        ws_config = set_provider_api_key(ws_config, provider, api_key, base_url)
        save_config(ws_config)
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
        if api_key:
            ws_config = set_provider_api_key(ws_config, provider, api_key, base_url)
        else:
            ws_config["api_key_set"] = bool(ws_config.get("provider_api_keys"))
        save_config(ws_config)
        state["ws_config"] = ws_config

    provider_summary = state["orchestrator"]._provider  # noqa: SLF001
    console.print(
        f"[green]Provider set:[/] [bold]{provider_summary.provider_name()}[/] "
        f"[green]Model:[/] [bold]{provider_summary.config.model}[/] "
        f"[green]Endpoint:[/] [bold]{provider_summary.config.base_url or '(provider default)'}[/]\n"
    )


def _manage_provider_keys(state: dict[str, Any], console) -> None:
    from limbi.workspace import (
        delete_provider_api_key,
        get_provider_api_key,
        save_config,
        set_provider_api_key,
    )

    while True:
        ws_config = state["ws_config"]
        provider_entries: list[dict[str, str]] = []
        for name, meta in _PROVIDER_CHOICES.items():
            base_url = str(meta.get("base_url") or "").strip()
            key = get_provider_api_key(ws_config, name, base_url)
            status = "saved" if key else "not saved"
            details = f"{meta['description']} ({status})"
            provider_entries.append({"name": name, "label": name, "details": details})

        provider_item = _select_from_menu(
            console,
            "Manage saved API keys",
            provider_entries,
            help_text="Pick a provider, then choose whether to set, update, or delete its saved key.",
        )
        provider = provider_item["name"]
        defaults = _PROVIDER_CHOICES.get(provider, {})
        base_url = str(defaults.get("base_url") or "").strip()
        if provider == "openai_compatible" or not base_url:
            base_url = click.prompt(
                "Choose base URL",
                default=base_url or str(state.get("base_url") or ""),
                show_default=bool(base_url or state.get("base_url")),
                type=str,
            ).strip()

        actions = [
            {"name": "set", "label": "Set or update key", "details": "save a new key for this provider"},
            {"name": "delete", "label": "Delete key", "details": "remove the saved key"},
            {"name": "back", "label": "Back", "details": "return to the terminal"},
        ]
        action_item = _select_from_menu(
            console,
            f"Key actions for {provider}",
            actions,
            help_text="Use Up/Down to move, then Enter to choose.",
        )
        action = action_item["name"]
        if action == "back":
            return

        if action == "set":
            api_key = click.prompt(
                f"Enter API key for {provider}",
                hide_input=True,
                confirmation_prompt=False,
                type=str,
            ).strip()
            if not api_key:
                raise click.ClickException("API key is required.")
            ws_config = set_provider_api_key(ws_config, provider, api_key, base_url)
            save_config(ws_config)
            state["ws_config"] = ws_config
            if state.get("provider") == provider and str(state.get("base_url") or "").strip() == base_url:
                state["api_key"] = api_key
                _setup_env_overrides(provider, state.get("model"), api_key, base_url)
                _refresh_orchestrator(state)
            console.print(f"[green]Saved API key for {provider}.[/]")
        else:
            had_key = bool(get_provider_api_key(ws_config, provider, base_url))
            ws_config = delete_provider_api_key(ws_config, provider, base_url)
            save_config(ws_config)
            state["ws_config"] = ws_config
            if state.get("provider") == provider and str(state.get("base_url") or "").strip() == base_url:
                state["api_key"] = ""
                _setup_env_overrides(provider, state.get("model"), None, base_url)
                _refresh_orchestrator(state)
            if had_key:
                console.print(f"[yellow]Deleted saved API key for {provider}.[/]")
            else:
                console.print(f"[dim]No saved API key existed for {provider}.[/]")
        if not click.confirm("Manage another saved key?", default=False):
            return


def _normalize_custom_skill_name(name: str) -> str:
    return str(name or "").strip().lower().replace(" ", "-")


def _custom_skill_runtime_summary(skill: dict[str, Any], state: dict[str, Any]) -> str:
    provider = str(skill.get("provider") or "").strip()
    model = str(skill.get("model") or "").strip()
    base_url = str(skill.get("base_url") or "").strip()
    if not provider:
        provider = str(state.get("provider") or "").strip() or "inherit"
    if not model:
        model = str(state.get("model") or "").strip() or "(current model)"
    summary = provider
    if model:
        summary += f" / {model}"
    if base_url:
        summary += f" @ {base_url}"
    elif not skill.get("provider"):
        summary += " (inherits current runtime)"
    return summary


def _print_custom_skills(console, state: dict[str, Any]) -> None:
    from rich.table import Table
    from limbi.workspace import get_custom_skills

    skills = get_custom_skills(state["ws_config"])
    table = Table(
        title="Saved Custom Skills",
        border_style="orange1",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Skill", style="bold white", min_width=18)
    table.add_column("Description", style="white", min_width=28)
    table.add_column("Runtime", style="dim", min_width=32)

    if not skills:
        table.add_row("(none)", "No custom skills have been saved yet.", "Use /skills to add one.")
        console.print(table)
        return

    for name, skill in sorted(skills.items()):
        table.add_row(
            name,
            str(skill.get("description") or "").strip() or "(no description)",
            _custom_skill_runtime_summary(skill, state),
        )
    console.print(table)


def _choose_custom_skill_runtime(state: dict[str, Any], console, existing_skill: dict[str, Any] | None = None) -> dict[str, str]:
    runtime_choices = [
        {
            "name": "__inherit__",
            "label": "Inherit current runtime",
            "details": "use the active provider, model, and endpoint when this skill runs",
        }
    ] + _provider_choice_items()
    default_provider = str(existing_skill.get("provider") or state.get("provider") or "ollama") if existing_skill else str(state.get("provider") or "ollama")
    default_index = 0
    for idx, item in enumerate(runtime_choices):
        if item["name"] == default_provider:
            default_index = idx
            break

    selected = _select_from_menu(
        console,
        "Choose runtime for this custom skill",
        runtime_choices,
        default_index=default_index,
        help_text="Use Up/Down to move, then Enter to choose.",
    )

    if selected["name"] == "__inherit__":
        return {"provider": "", "model": "", "base_url": ""}

    provider = selected["name"]
    defaults = _PROVIDER_CHOICES.get(provider, {})
    base_url = str(defaults.get("base_url") or "").strip()
    if provider == "openai_compatible":
        base_url = click.prompt(
            "Custom base URL",
            default=str(existing_skill.get("base_url") or state.get("base_url") or base_url or ""),
            show_default=bool(existing_skill.get("base_url") or state.get("base_url") or base_url),
            type=str,
        ).strip()
    model = click.prompt(
        "Model for this skill",
        default=str(existing_skill.get("model") or defaults.get("model") or state.get("model") or "llama3.2:3b"),
        show_default=True,
        type=str,
    ).strip()
    return {"provider": provider, "model": model, "base_url": base_url}


def _delete_custom_skill(state: dict[str, Any], console, skill_name: str) -> None:
    from limbi.workspace import delete_custom_skill, get_custom_skills, save_config

    skill_key = _normalize_custom_skill_name(skill_name)
    ws_config = dict(state["ws_config"])
    skills = get_custom_skills(ws_config)
    if skill_key not in skills:
        console.print(f"[yellow]No saved custom skill named '{skill_key}'.[/]")
        return
    if not click.confirm(f"Delete custom skill '{skill_key}'?", default=False):
        return
    ws_config = delete_custom_skill(ws_config, skill_key)
    save_config(ws_config)
    state["ws_config"] = ws_config
    console.print(f"[green]Deleted custom skill:[/] [bold]{skill_key}[/]")


def _save_custom_skill(
    state: dict[str, Any],
    console,
    name: str,
    *,
    existing_skill: dict[str, Any] | None = None,
) -> None:
    from limbi.workspace import get_custom_skill, save_config, set_custom_skill
    from rich.panel import Panel

    ws_config = dict(state["ws_config"])
    existing = existing_skill or get_custom_skill(ws_config, name)

    description = click.prompt(
        "Short description",
        default=str(existing.get("description") or ""),
        show_default=bool(existing.get("description")),
        type=str,
    ).strip()
    instruction = click.prompt(
        "Skill instruction",
        default=str(existing.get("instruction") or ""),
        show_default=bool(existing.get("instruction")),
        type=str,
    ).strip()
    runtime = _choose_custom_skill_runtime(state, console, existing_skill=existing)

    ws_config = set_custom_skill(
        ws_config,
        name,
        {
            "description": description,
            "instruction": instruction,
            "provider": runtime.get("provider", ""),
            "model": runtime.get("model", ""),
            "base_url": runtime.get("base_url", ""),
        },
    )
    save_config(ws_config)
    state["ws_config"] = ws_config
    saved = get_custom_skill(ws_config, name)
    console.print(
        Panel(
            f"[green]Saved custom skill:[/] [bold]{saved.get('name', _normalize_custom_skill_name(name))}[/]\n"
            f"[dim]Runtime:[/] { _custom_skill_runtime_summary(saved, state) }\n"
            f"[dim]Instruction:[/] {saved.get('instruction', '')[:200]}",
            border_style="orange1",
            title="Custom Skill Saved",
            padding=(1, 2),
        )
    )


def _manage_custom_skills(state: dict[str, Any], console) -> None:
    from limbi.workspace import get_custom_skill, get_custom_skills

    while True:
        _print_custom_skills(console, state)
        actions = [
            {"name": "create", "label": "Create skill", "details": "define a new reusable prompt skill"},
            {"name": "update", "label": "Update skill", "details": "edit an existing saved skill"},
            {"name": "delete", "label": "Delete skill", "details": "remove a saved skill"},
            {"name": "back", "label": "Back", "details": "return to the terminal"},
        ]
        action_item = _select_from_menu(
            console,
            "Custom skills",
            actions,
            help_text="Use Up/Down to move, then Enter to choose.",
        )
        action = action_item["name"]
        if action == "back":
            return

        ws_config = dict(state["ws_config"])
        skills = get_custom_skills(ws_config)

        if action == "delete":
            if not skills:
                console.print("[dim]No custom skills to delete.[/]")
                continue
            delete_item = _select_from_menu(
                console,
                "Delete which skill?",
                [
                    {"name": name, "label": name, "details": str(skill.get("description") or "").strip() or "(no description)"}
                    for name, skill in sorted(skills.items())
                ],
                help_text="Use Up/Down to move, then Enter to choose.",
            )
            _delete_custom_skill(state, console, delete_item["name"])
            if not click.confirm("Manage another custom skill?", default=False):
                return
            continue

        if action == "update":
            if not skills:
                console.print("[dim]No custom skills to update yet.[/]")
                continue
            selected_skill = _select_from_menu(
                console,
                "Update which skill?",
                [
                    {"name": name, "label": name, "details": str(skill.get("description") or "").strip() or "(no description)"}
                    for name, skill in sorted(skills.items())
                ],
                help_text="Use Up/Down to move, then Enter to choose.",
            )
            name = selected_skill["name"]
            existing_skill = get_custom_skill(ws_config, name)
        else:
            name = click.prompt(
            "Skill name (used as /skill-name)",
            default="",
            show_default=False,
            type=str,
            ).strip()
            if not name:
                raise click.ClickException("Skill name is required.")
            existing_skill = get_custom_skill(ws_config, name)

        _save_custom_skill(state, console, name, existing_skill=existing_skill)
        if not click.confirm("Manage another custom skill?", default=False):
            return


def _run_custom_skill(state: dict[str, Any], console, skill_name: str, task_text: str | None = None) -> None:
    from limbi.workspace import get_custom_skill

    skill = get_custom_skill(state["ws_config"], skill_name)
    if not skill:
        console.print(f"[red]No custom skill named '{_normalize_custom_skill_name(skill_name)}' was found.[/]")
        return

    instruction = str(skill.get("instruction") or "").strip()
    if not instruction:
        console.print(f"[red]Custom skill '{skill.get('name', skill_name)}' has no instruction saved.[/]")
        return

    task = str(task_text or "").strip()
    if not task:
        task = click.prompt(
            f"Describe what you want '{skill.get('name', skill_name)}' to do",
            type=str,
        ).strip()
    if not task:
        raise click.ClickException("A task description is required to run a custom skill.")

    current_provider = str(state.get("provider") or os.environ.get("LLM_PROVIDER", "ollama")).strip()
    current_model = str(state.get("model") or os.environ.get("LLM_MODEL", "")).strip()
    current_base_url = str(state.get("base_url") or os.environ.get("LLM_BASE_URL", "")).strip()
    current_api_key = str(state.get("api_key") or os.environ.get("LLM_API_KEY", "")).strip()

    runtime_provider = str(skill.get("provider") or current_provider or "ollama").strip()
    runtime_model = str(skill.get("model") or current_model or "").strip()
    runtime_base_url = str(skill.get("base_url") or _provider_base_url(runtime_provider, state)).strip()
    runtime_api_key = current_api_key
    if runtime_provider != current_provider or runtime_base_url != current_base_url:
        runtime_api_key = ""

    composed_prompt = "\n\n".join(
        [
            f"You are running the custom skill '{skill.get('name', _normalize_custom_skill_name(skill_name))}'.",
            f"Instruction:\n{instruction}",
            f"Task:\n{task}",
        ]
    )

    try:
        _setup_env_overrides(runtime_provider, runtime_model, runtime_api_key or None, runtime_base_url)
        state["provider"] = runtime_provider
        state["model"] = runtime_model
        state["base_url"] = runtime_base_url
        state["api_key"] = runtime_api_key
        _refresh_orchestrator(state)
        asyncio.run(_send_message(state, composed_prompt, console))
    finally:
        _setup_env_overrides(current_provider, current_model, current_api_key or None, current_base_url)
        state["provider"] = current_provider
        state["model"] = current_model
        state["base_url"] = current_base_url
        state["api_key"] = current_api_key
        _refresh_orchestrator(state)


def _run_evaluation_suite(state: dict[str, Any], console) -> None:
    from rich.panel import Panel
    from rich.table import Table

    from limbi.evaluation import run_evaluation_suite

    console.print("[bold orange1]Running evaluation suite...[/]")
    result = asyncio.run(run_evaluation_suite())
    benchmark = result.get("benchmark", {})
    cases = result.get("cases", [])

    table = Table(title="Evaluation Results", border_style="orange1", show_lines=False)
    table.add_column("Case", style="bold white")
    table.add_column("Status", style="white")
    table.add_column("Score", justify="right", style="white")
    table.add_column("Notes", style="dim")
    for case in cases:
        table.add_row(
            str(case.get("name", "")),
            str(case.get("status", "")),
            f"{float(case.get('score', 0.0)):.2f}",
            str(case.get("note", "")),
        )

    console.print(table)
    console.print(
        Panel(
            f"Score: {float(benchmark.get('score', 0.0)):.3f}   "
            f"Passed: {benchmark.get('passed', 0)}   "
            f"Skipped: {benchmark.get('skipped', 0)}   "
            f"Failed: {benchmark.get('failed', 0)}",
            title="[bold orange1]Benchmark[/]",
            border_style="orange1",
            padding=(0, 1),
        )
    )


def _print_permission_policy(console, state: dict[str, Any]) -> None:
    from rich.table import Table
    from limbi.workspace import get_permission_policy

    policy = get_permission_policy(state.get("ws_config", {}))
    table = Table(title="Permission Policy", border_style="orange1")
    table.add_column("Scope", style="bold white")
    table.add_column("Actor", style="white")
    table.add_column("Mode", style="white")
    for scope, entries in policy.items():
        if not isinstance(entries, dict):
            continue
        for actor, mode in entries.items():
            table.add_row(scope, actor, str(mode))
    console.print(table)
    console.print()


def _print_recent_traces(console, limit: int = 10) -> None:
    from rich.table import Table
    from limbi.tracing import list_traces

    traces = list_traces(limit=limit)
    table = Table(title="Recent Traces", border_style="orange1", show_lines=False)
    table.add_column("Trace ID", style="bold white")
    table.add_column("Route", style="white")
    table.add_column("Status", style="white")
    table.add_column("Model", style="dim")
    table.add_column("Tokens", style="dim", justify="right")
    table.add_column("Search", style="dim")

    if not traces:
        table.add_row("(none)", "-", "-", "-", "0", "-")
        console.print(table)
        return

    for trace in traces:
        table.add_row(
            str(trace.get("trace_id") or "")[:12],
            str(trace.get("route") or "-"),
            str(trace.get("status") or "-"),
            str(trace.get("model") or "-"),
            str(int(trace.get("total_tokens") or 0)),
            str(trace.get("search_path") or "-"),
        )
    console.print(table)
    console.print()


def _print_trace_detail(console, trace_id: str) -> None:
    from rich.panel import Panel
    from rich.table import Table
    from limbi.tracing import get_trace

    trace = get_trace(trace_id)
    if not trace:
        console.print(f"[yellow]No trace found for '{trace_id}'.[/]")
        return

    header = Table.grid(padding=(0, 1))
    header.add_row("Trace ID", str(trace.get("trace_id") or trace_id))
    header.add_row("Status", str(trace.get("status") or ""))
    header.add_row("Route", str(trace.get("route") or ""))
    header.add_row("Route reason", str(trace.get("route_reason") or ""))
    header.add_row("Route confidence", f"{float(trace.get('route_confidence') or 0.0):.2f}")
    header.add_row("Model", str(trace.get("model") or ""))
    header.add_row("Search path", str(trace.get("search_path") or ""))
    header.add_row("Tokens", str(int(trace.get("total_tokens") or 0)))
    header.add_row("Sources", str(int(trace.get("research_source_count") or 0)))
    header.add_row("Prompt", str(trace.get("prompt") or ""))

    console.print(Panel(header, title="[bold orange1]Trace[/]", border_style="orange1", padding=(1, 2)))

    events = trace.get("events") or []
    if events:
        table = Table(title="Trace Events", border_style="orange1", show_lines=False)
        table.add_column("Time", style="dim")
        table.add_column("Kind", style="bold white")
        table.add_column("Status", style="white")
        table.add_column("Agent", style="white")
        table.add_column("Action", style="white")
        table.add_column("Message", style="white")
        for event in events:
            table.add_row(
                str(event.get("timestamp") or ""),
                str(event.get("kind") or ""),
                str(event.get("status") or ""),
                str(event.get("agent") or ""),
                str(event.get("action") or ""),
                str(event.get("message") or ""),
            )
        console.print(table)
    console.print()


def _export_custom_skill(state: dict[str, Any], console, skill_name: str, output_path: str | None = None) -> None:
    from limbi.workspace import export_custom_skill

    skill_key = _normalize_custom_skill_name(skill_name)
    skill = export_custom_skill(state["ws_config"], skill_key)
    if not skill:
        console.print(f"[yellow]No saved custom skill named '{skill_key}'.[/]")
        return

    payload = json.dumps(skill, indent=2) + "\n"
    if output_path:
        Path(output_path).expanduser().write_text(payload, encoding="utf-8")
        console.print(f"[green]Exported custom skill:[/] [bold]{skill_key}[/] -> {output_path}")
    else:
        console.print(payload)


def _import_custom_skill(state: dict[str, Any], console, input_path: str) -> None:
    from limbi.workspace import import_custom_skill, save_config

    path = Path(input_path).expanduser()
    if not path.exists():
        console.print(f"[red]Skill file not found:[/] {path}")
        return

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        console.print(f"[red]Invalid skill JSON:[/] {exc}")
        return

    state["ws_config"] = import_custom_skill(state["ws_config"], payload)
    save_config(state["ws_config"])
    skill_name = _normalize_custom_skill_name(str(payload.get("name") or payload.get("skill_name") or "skill"))
    console.print(f"[green]Imported custom skill:[/] [bold]{skill_name}[/]")


def _export_custom_skill_pack(state: dict[str, Any], console, skill_name: str, output_path: str | None = None) -> None:
    from limbi.workspace import export_custom_skill_pack

    skill_key = _normalize_custom_skill_name(skill_name)
    pack = export_custom_skill_pack(state["ws_config"], skill_key)
    if not pack:
        console.print(f"[yellow]No saved custom skill named '{skill_key}'.[/]")
        return

    payload = json.dumps(pack, indent=2) + "\n"
    if output_path:
        Path(output_path).expanduser().write_text(payload, encoding="utf-8")
        console.print(f"[green]Exported custom skill pack:[/] [bold]{skill_key}[/] -> {output_path}")
    else:
        console.print(payload)


def _import_custom_skill_pack(state: dict[str, Any], console, input_path: str) -> None:
    from limbi.workspace import import_custom_skill_pack, save_config

    path = Path(input_path).expanduser()
    if not path.exists():
        console.print(f"[red]Skill pack file not found:[/] {path}")
        return

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        console.print(f"[red]Invalid skill pack JSON:[/] {exc}")
        return

    state["ws_config"] = import_custom_skill_pack(state["ws_config"], payload)
    save_config(state["ws_config"])
    skill_name = _normalize_custom_skill_name(str((payload.get("manifest") or {}).get("name") or (payload.get("skill") or {}).get("name") or "skill"))
    console.print(f"[green]Imported custom skill pack:[/] [bold]{skill_name}[/]")


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


def _prompt_missing_contract_params(agent, action: str, params: dict[str, Any], console) -> dict[str, Any]:
    contract = getattr(agent, "action_contract", lambda _action: None)(action)
    if not contract:
        return params

    schema = contract.input_schema or {}
    properties = schema.get("properties", {})
    required = list(schema.get("required", []))

    for field_name in required:
        if field_name in params:
            continue
        field_schema = properties.get(field_name, {})
        field_type = str(field_schema.get("type") or "string")
        default_value = field_schema.get("default", _MISSING)
        prompt_text = f"Enter value for {field_name}"

        if field_type == "integer":
            params[field_name] = click.prompt(
                prompt_text,
                default=default_value if default_value is not _MISSING else None,
                type=int,
                show_default=default_value is not _MISSING,
            )
        elif field_type == "number":
            params[field_name] = click.prompt(
                prompt_text,
                default=default_value if default_value is not _MISSING else None,
                type=float,
                show_default=default_value is not _MISSING,
            )
        elif field_type == "boolean":
            params[field_name] = click.confirm(
                f"{field_name}?",
                default=bool(default_value) if default_value is not _MISSING else False,
            )
        elif field_type in {"array", "object"}:
            raw = click.prompt(
                f"Enter JSON for {field_name}",
                default="[]" if field_type == "array" else "{}",
                show_default=True,
                type=str,
            )
            try:
                params[field_name] = _parse_json_params(raw) if field_type == "object" else json.loads(raw)
            except json.JSONDecodeError as exc:
                raise click.ClickException(f"Invalid JSON for '{field_name}': {exc}") from exc
            if field_type == "array" and not isinstance(params[field_name], list):
                raise click.ClickException(f"Parameter '{field_name}' must be a JSON array.")
        else:
            params[field_name] = click.prompt(
                prompt_text,
                default=str(default_value) if default_value is not _MISSING else "",
                show_default=default_value is not _MISSING,
                type=str,
            )

    return params


def _run_manual_agent(state: dict[str, Any], console) -> None:
    from limbi.agents import get_agent, list_agents
    from limbi.agents.context_memory_agent import get_shared_state_value
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
    session_id = str(state.get("session_id") or "global")
    if agent_name == "learning_agent" and action == "get_best_action":
        session_state = get_shared_state_value(session_id).get("state", {})
        params.setdefault(
            "state",
            str(
                session_state.get("current_focus")
                or session_state.get("current_goal")
                or "general"
            ),
        )
        params.setdefault(
            "available_actions",
            [name for name in agent.available_actions if name != "get_best_action"],
        )
    elif agent_name == "learning_agent" and action == "record_feedback":
        session_state = get_shared_state_value(session_id).get("state", {})
        params.setdefault(
            "state",
            str(
                session_state.get("current_focus")
                or session_state.get("current_goal")
                or "general"
            ),
        )
    params = _prompt_missing_contract_params(agent, action, params, console)
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


def _resolve_api_key(provider: str | None, api_key: str | None, base_url: str | None = None) -> str | None:
    resolved_provider = (provider or os.environ.get("LLM_PROVIDER", "ollama")).strip().lower()
    resolved_base_url = (base_url or os.environ.get("LLM_BASE_URL", "")).strip()
    resolved_key = (api_key or os.environ.get("LLM_API_KEY", "")).strip()

    if not provider_requires_api_key(resolved_provider, resolved_base_url):
        return None

    from limbi.workspace import get_provider_api_key, save_config, set_provider_api_key

    ws_config = None
    try:
        from limbi.workspace import load_config

        ws_config = load_config()
    except Exception:
        ws_config = None

    if not resolved_key and ws_config is not None:
        resolved_key = get_provider_api_key(ws_config, resolved_provider, resolved_base_url)

    if resolved_key and ws_config is not None:
        updated_config = set_provider_api_key(ws_config, resolved_provider, resolved_key, resolved_base_url)
        save_config(updated_config)

    return resolved_key or None


def _is_parser_noise(error: str) -> bool:
    return error.startswith(
        (
            "JSONDecodeError:",
            "Unexpected JSON type:",
            "Validation error:",
        )
    )


async def _status_ticker(status, stop_event: asyncio.Event, status_state: dict[str, str]) -> None:
    started = time.perf_counter()
    while not stop_event.is_set():
        elapsed = time.perf_counter() - started
        stage = str(status_state.get("message") or "Thinking").strip()
        if not stage:
            stage = "Thinking"
        status.update(f"[bold orange1]{stage}... {elapsed:.1f}s[/]")
        try:
            await asyncio.sleep(0.8)
        except asyncio.CancelledError:
            return


async def _send_message(state, message: str, console) -> None:
    from rich.markdown import Markdown
    from rich.panel import Panel

    stop_event = asyncio.Event()
    status_state = {"message": "Planning task"}

    def _update_progress(stage: str) -> None:
        clean = str(stage or "").strip()
        if clean:
            status_state["message"] = clean

    with console.status("[bold orange1]Thinking...[/]", spinner="dots") as status:
        ticker = asyncio.create_task(_status_ticker(status, stop_event, status_state))
        try:
            _ensure_runtime_api_key(state, console)
            result = await state["orchestrator"].chat(message, progress_callback=_update_progress)
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
        summary.append("    ", style="white")
        summary.append("complexity: ", style="bold orange1")
        summary.append(str(metrics.get("task_complexity", "moderate")), style="white")
        summary.append("    ", style="white")
        summary.append("budget: ", style="bold orange1")
        summary.append(str(metrics.get("runtime_token_budget", 0)), style="white")
        summary.append("    ", style="white")
        summary.append("route: ", style="bold orange1")
        summary.append(str(metrics.get("task_route", "direct")), style="white")
        route_confidence = metrics.get("route_confidence")
        if route_confidence is not None:
            summary.append(" ", style="white")
            summary.append(f"({float(route_confidence) * 100:.0f}% confidence)", style="dim")
        route_reason = str(metrics.get("route_reason", "")).strip()
        if route_reason:
            summary.append(" ", style="white")
            summary.append(f"[{route_reason}]", style="dim")
        effective_model = str(metrics.get("effective_model", "")).strip()
        if effective_model:
            summary.append("    ", style="white")
            summary.append("model: ", style="bold orange1")
            summary.append(effective_model, style="white")
        trace_id = str(metrics.get("trace_id", "")).strip()
        if trace_id:
            summary.append("    ", style="white")
            summary.append("trace: ", style="bold orange1")
            summary.append(trace_id, style="white")
        search_path = str(metrics.get("search_path", "")).strip()
        if search_path:
            summary.append("    ", style="white")
            summary.append("search: ", style="bold orange1")
            summary.append(search_path, style="white")
        source_count = int(metrics.get("research_source_count", 0) or 0)
        if source_count:
            summary.append("    ", style="white")
            summary.append("sources: ", style="bold orange1")
            summary.append(str(source_count), style="white")
        console.print(Panel(summary, border_style="orange1", padding=(0, 1)))


def _repl(state, console):
    from rich.markdown import Markdown
    from limbi.workspace import get_custom_skills

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
            parts = user_input.strip().split(maxsplit=2)
            cmd = parts[0].lower()
            if cmd in ("/quit", "/exit", "/q"):
                console.print("Goodbye.")
                break
            if cmd in ("/skills",):
                subcommand = parts[1].lower() if len(parts) > 1 else ""
                if subcommand in {"list", "show"}:
                    _print_custom_skills(console, state)
                elif subcommand == "export":
                    if len(parts) < 3:
                        console.print("[yellow]Use /skills export <name> [output.json][/]")
                    else:
                        output_path = parts[3] if len(parts) > 3 else None
                        _export_custom_skill(state, console, parts[2], output_path=output_path)
                elif subcommand == "import":
                    if len(parts) < 3:
                        console.print("[yellow]Use /skills import <skill.json>[/]")
                    else:
                        _import_custom_skill(state, console, parts[2])
                elif subcommand == "pack" and len(parts) > 2:
                    pack_action = parts[2].lower()
                    if pack_action == "export":
                        if len(parts) < 4:
                            console.print("[yellow]Use /skills pack export <name> [output.json][/]")
                        else:
                            output_path = parts[4] if len(parts) > 4 else None
                            _export_custom_skill_pack(state, console, parts[3], output_path=output_path)
                    elif pack_action == "import":
                        if len(parts) < 4:
                            console.print("[yellow]Use /skills pack import <skill-pack.json>[/]")
                        else:
                            _import_custom_skill_pack(state, console, parts[3])
                    else:
                        console.print("[yellow]Use /skills pack export ... or /skills pack import ...[/]")
                elif subcommand in {"update", "edit"} and len(parts) > 2:
                    from limbi.workspace import get_custom_skill

                    skill_name = parts[2]
                    skill = get_custom_skill(state["ws_config"], skill_name)
                    if not skill:
                        console.print(f"[yellow]No saved custom skill named '{_normalize_custom_skill_name(skill_name)}'.[/]")
                    else:
                        _save_custom_skill(state, console, skill_name, existing_skill=skill)
                elif subcommand in {"delete", "remove"} and len(parts) > 2:
                    _delete_custom_skill(state, console, parts[2])
                else:
                    _manage_custom_skills(state, console)
                continue
            if cmd in ("/skill",):
                if len(parts) < 2:
                    console.print("[yellow]Use /skill <name> [task][/]")
                    continue
                skill_name = parts[1]
                task_text = parts[2] if len(parts) > 2 else ""
                _run_custom_skill(state, console, skill_name, task_text=task_text)
                continue
            if cmd in ("/agent",):
                _run_manual_agent(state, console)
                continue
            if cmd in ("/agents",):
                _run_manual_agent(state, console)
                continue
            if cmd in ("/list",):
                _print_agent_table(console)
                continue
            if cmd in ("/model",):
                _configure_runtime_from_model_choice(state, console)
                continue
            if cmd in ("/keys", "/key"):
                _manage_provider_keys(state, console)
                continue
            if cmd in ("/eval", "/benchmark"):
                _run_evaluation_suite(state, console)
                continue
            if cmd in ("/permissions",):
                subcommand = parts[1].lower() if len(parts) > 1 else "show"
                if subcommand in {"show", "list"}:
                    _print_permission_policy(console, state)
                elif len(parts) >= 4:
                    from limbi.workspace import save_config, set_permission_policy

                    scope = parts[1]
                    actor = parts[2]
                    mode = parts[3]
                    state["ws_config"] = set_permission_policy(state["ws_config"], scope, actor, mode)
                    save_config(state["ws_config"])
                    console.print(f"[green]Permission updated:[/] {scope}:{actor} -> {mode}\n")
                else:
                    console.print("[yellow]Use /permissions show or /permissions <scope> <actor> <mode>[/]")
                continue
            if cmd in ("/traces",):
                _print_recent_traces(console)
                continue
            if cmd in ("/trace",):
                if len(parts) > 1:
                    _print_trace_detail(console, parts[1])
                else:
                    _print_recent_traces(console, limit=5)
                    console.print("[dim]Use /trace <trace_id> for the full event log.[/]")
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
| `/models` | Choose provider and model for the current session |
| `/keys` | Manage saved API keys for providers |
| `/skills` | Open the custom skill manager |
| `/skill` | Run a saved custom skill with a task |
| `/agents` | Manually choose an agent and run one action |
| `/agent` | Alias for `/agents` |
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

            custom_skills = get_custom_skills(state["ws_config"])
            skill_name = _normalize_custom_skill_name(cmd.lstrip("/"))
            if skill_name in custom_skills:
                task_text = user_input[len(parts[0]):].strip()
                _run_custom_skill(state, console, skill_name, task_text=task_text)
                continue

        asyncio.run(_send_message(state, user_input, console))


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
@click.version_option(version="1.6.1", prog_name="limbi")
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

    api_key = _resolve_api_key(provider, api_key, os.environ.get("LLM_BASE_URL"))
    ws_config = load_config()
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
    session_id = f"session-{uuid.uuid4().hex[:12]}"
    orchestrator = Orchestrator(session_id=session_id)

    provider_obj = _limbi.get_llm_provider()
    state = {
        "orchestrator": orchestrator,
        "session_id": session_id,
        "provider": provider_obj.provider_name(),
        "model": provider_obj.config.model,
        "base_url": provider_obj.config.base_url,
        "api_key": provider_obj.config.api_key,
        "ws_config": ws_config,
        "save_config": save_config,
    }
    try:
        orchestrator._sync_session_state()  # noqa: SLF001
    except Exception:
        pass
    console.print(
        f"[dim]Provider:[/] [bold]{provider_obj.provider_name()}[/] "
        f"[dim]Model:[/] [bold]{provider_obj.config.model}[/] "
        f"[dim]Agents:[/] [bold]{len(_limbi.list_agents())}[/]"
        f"[dim] Workspace:[/] [bold]{ws_result['workspace']}[/]\n"
    )

    if prompt:
        asyncio.run(_send_message(state, prompt, console))
    else:
        _repl(state, console)


if __name__ == "__main__":
    main()
