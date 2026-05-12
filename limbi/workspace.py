
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("limbi.workspace")

WORKSPACE_DIR_NAME = ".limbi"

_DEFAULT_CONFIG = {
    "version": "1.2.0",
    "created_at": "",
    "provider": "ollama",
    "model": "llama3.2:3b",
    "base_url": "http://localhost:11434",
    "temperature": 0.2,
    "max_tokens": 2048,
    "session_ttl_hours": 24,
    "auto_publish_context": True,
}


def get_workspace_path(base_dir: str | None = None) -> Path:
    base = Path(base_dir).expanduser().resolve() if base_dir else Path.cwd().resolve()
    return base / WORKSPACE_DIR_NAME


def init_workspace(base_dir: str | None = None) -> dict[str, Any]:
    ws = get_workspace_path(base_dir)
    is_new = not ws.exists()
    created: list[str] = []
    existing: list[str] = []

    dirs = [
        ws,
        ws / "sessions",
        ws / "chroma_db",
        ws / "logs",
    ]
    for d in dirs:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(str(d.relative_to(ws.parent)))
        else:
            existing.append(str(d.relative_to(ws.parent)))

    config_path = ws / "config.json"
    if not config_path.exists():
        config = {**_DEFAULT_CONFIG}
        config["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        config["provider"] = os.getenv("LLM_PROVIDER", config["provider"])
        config["model"] = os.getenv("LLM_MODEL", config["model"])
        config["base_url"] = os.getenv("LLM_BASE_URL", config["base_url"])
        if os.getenv("LLM_API_KEY"):
            config["api_key_set"] = True

        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        created.append(".limbi/config.json")
    else:
        existing.append(".limbi/config.json")

    gitignore_path = ws / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(
            "# Limbi workspace — auto-generated\n"
            "# Keep config.json in version control if desired\n"
            "*.db\n"
            "*.db-wal\n"
            "*.db-shm\n"
            "chroma_db/\n"
            "sessions/\n"
            "logs/\n",
            encoding="utf-8",
        )
        created.append(".limbi/.gitignore")

    _set_workspace_env(ws)

    logger.info(
        "Workspace %s at %s (created: %d, existing: %d)",
        "initialized" if is_new else "loaded",
        ws,
        len(created),
        len(existing),
    )

    return {
        "workspace": str(ws),
        "is_new": is_new,
        "created": created,
        "existing": existing,
    }


def _set_workspace_env(ws: Path) -> None:
    defaults = {
        "AUDIT_DB_PATH": str(ws / "audit.db"),
        "MEMORY_DB_PATH": str(ws / "memory.db"),
        "CONTEXT_MEMORY_DB_PATH": str(ws / "context_memory.db"),
        "CHROMA_PERSIST_DIR": str(ws / "chroma_db"),
    }
    for key, path in defaults.items():
        if not os.environ.get(key):
            os.environ[key] = path


def load_config(base_dir: str | None = None) -> dict[str, Any]:
    ws = get_workspace_path(base_dir)
    config_path = ws / "config.json"

    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read config: %s", exc)

    return dict(_DEFAULT_CONFIG)


def save_config(config: dict[str, Any], base_dir: str | None = None) -> None:
    ws = get_workspace_path(base_dir)
    config_path = ws / "config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def get_db_path(name: str) -> str:
    ws = get_workspace_path()
    return str(ws / name)


def workspace_info() -> dict[str, Any]:
    ws = get_workspace_path()
    if not ws.exists():
        return {
            "initialized": False,
            "path": str(ws),
            "root_path": str(ws.parent),
            "workspace_name": ws.name,
        }

    config = load_config()

    db_files = list(ws.glob("*.db"))
    total_db_size = sum(f.stat().st_size for f in db_files if f.exists())

    return {
        "initialized": True,
        "path": str(ws),
        "root_path": str(ws.parent),
        "workspace_name": ws.name,
        "config": config,
        "databases": [f.name for f in db_files],
        "total_db_size_mb": round(total_db_size / (1024 * 1024), 2),
        "has_vector_store": (ws / "chroma_db").exists(),
    }
