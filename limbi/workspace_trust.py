from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("limbi.workspace_trust")

_TRUST_STORE_DIR = Path.home() / ".limbi"
_TRUST_STORE_PATH = _TRUST_STORE_DIR / "trusted_workspaces.json"


def _load_trust_store() -> dict[str, Any]:
    if _TRUST_STORE_PATH.exists():
        try:
            return json.loads(_TRUST_STORE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read trust store: %s", exc)
    return {"version": 1, "workspaces": {}}


def _save_trust_store(store: dict[str, Any]) -> None:
    _TRUST_STORE_DIR.mkdir(parents=True, exist_ok=True)
    _TRUST_STORE_PATH.write_text(
        json.dumps(store, indent=2) + "\n", encoding="utf-8"
    )


def _resolve_workspace(path: str | Path | None = None) -> str:
    ws = Path(path) if path else Path.cwd()
    return str(ws.resolve())


def is_workspace_trusted(path: str | Path | None = None) -> bool:
    resolved = _resolve_workspace(path)
    store = _load_trust_store()
    entry = store.get("workspaces", {}).get(resolved)
    if entry and entry.get("trust_level") in ("full", "readonly"):
        return True
    return False


def get_trust_level(path: str | Path | None = None) -> str | None:
    resolved = _resolve_workspace(path)
    store = _load_trust_store()
    entry = store.get("workspaces", {}).get(resolved)
    if entry:
        return entry.get("trust_level")
    return None


def set_workspace_trust(
    path: str | Path | None = None,
    trust_level: str = "full",
) -> dict[str, Any]:
    resolved = _resolve_workspace(path)
    store = _load_trust_store()

    store.setdefault("workspaces", {})[resolved] = {
        "trust_level": trust_level,
        "trusted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cwd_at_trust": resolved,
    }

    _save_trust_store(store)
    logger.info("Workspace trust set: %s -> %s", resolved, trust_level)
    return {"path": resolved, "trust_level": trust_level}


def revoke_workspace_trust(path: str | Path | None = None) -> dict[str, Any]:
    resolved = _resolve_workspace(path)
    store = _load_trust_store()

    if resolved in store.get("workspaces", {}):
        del store["workspaces"][resolved]
        _save_trust_store(store)
        return {"path": resolved, "revoked": True}
    return {"path": resolved, "revoked": False, "message": "Was not trusted"}


def list_trusted_workspaces() -> list[dict[str, Any]]:
    store = _load_trust_store()
    result = []
    for ws_path, entry in store.get("workspaces", {}).items():
        result.append({
            "path": ws_path,
            "trust_level": entry.get("trust_level", "unknown"),
            "trusted_at": entry.get("trusted_at", ""),
        })
    return result


def prompt_workspace_trust(
    path: str | Path | None = None,
    console: Any = None,
) -> str:
    resolved = _resolve_workspace(path)

    existing = get_trust_level(resolved)
    if existing in ("full", "readonly"):
        return existing

    if console is None:
        try:
            from rich.console import Console
            console = Console()
        except ImportError:
            return _prompt_plain(resolved)

    from rich.panel import Panel
    from rich.text import Text

    body = Text()
    body.append("Workspace Trust Required\n\n", style="bold yellow")
    body.append("Limbi wants to operate in:\n", style="")
    body.append(f"  {resolved}\n\n", style="bold white")
    body.append(
        "Limbi agents can read, write, and execute files within this\n"
        "workspace. Only trust workspaces you control.\n\n",
        style="dim",
    )
    body.append("Options:\n", style="")
    body.append("  [Y] Yes, trust fully    ", style="bold green")
    body.append("(read + write + execute)\n", style="dim")
    body.append("  [R] Read-only           ", style="bold cyan")
    body.append("(read only, no writes)\n", style="dim")
    body.append("  [N] No, exit            ", style="bold red")
    body.append("(do not trust, exit Limbi)\n", style="dim")

    console.print(Panel(body, border_style="yellow", padding=(1, 2)))

    while True:
        try:
            choice = console.input(
                "[bold yellow]Do you trust this workspace?[/] [Y/R/N]: "
            ).strip().upper()
        except (EOFError, KeyboardInterrupt):
            choice = "N"

        if choice in ("Y", "YES"):
            trust_level = "full"
            set_workspace_trust(resolved, trust_level)
            console.print(
                f"\n[bold green]Workspace [bold]{resolved}[/] "
                f"trusted ([green]full access[/]).\n"
            )
            return trust_level

        elif choice in ("R", "READONLY", "READ"):
            trust_level = "readonly"
            set_workspace_trust(resolved, trust_level)
            console.print(
                f"\n[bold cyan]Workspace [bold]{resolved}[/] "
                f"trusted ([cyan]read-only[/]).\n"
            )
            return trust_level

        elif choice in ("N", "NO", ""):
            console.print(
                "\n[bold red]Workspace not trusted. "
                "[dim]Limbi will not operate in untrusted workspaces.[/]\n"
            )
            sys.exit(1)

        else:
            console.print("[dim]Please enter Y, R, or N.[/]")


def _prompt_plain(resolved: str) -> str:
    print(f"\nWorkspace Trust Required")
    print(f"   Limbi wants to operate in: {resolved}")
    print(f"   [Y] Yes, trust fully | [R] Read-only | [N] No, exit")

    while True:
        try:
            choice = input("Do you trust this workspace? [Y/R/N]: ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            choice = "N"

        if choice in ("Y", "YES"):
            set_workspace_trust(resolved, "full")
            print(f"Workspace trusted (full access).\n")
            return "full"
        elif choice in ("R", "READONLY", "READ"):
            set_workspace_trust(resolved, "readonly")
            print(f"Workspace trusted (read-only).\n")
            return "readonly"
        elif choice in ("N", "NO", ""):
            print("Workspace not trusted. Exiting.\n")
            sys.exit(1)
        else:
            print("Please enter Y, R, or N.")


def check_workspace_trust(
    path: str | Path | None = None,
    console: Any = None,
    skip_prompt: bool = False,
) -> str:
    resolved = _resolve_workspace(path)
    existing = get_trust_level(resolved)

    if existing == "denied":
        if not skip_prompt:
            if console:
                console.print(
                    "\n[bold red]This workspace was previously denied. "
                    "[dim]Run [bold]limbi --trust-reset[/] to re-prompt.[/]\n"
                )
            sys.exit(1)
        return "denied"

    if existing in ("full", "readonly"):
        return existing

    if skip_prompt:
        return "untrusted"

    return prompt_workspace_trust(resolved, console)
