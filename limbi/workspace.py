
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("limbi.workspace")

WORKSPACE_DIR_NAME = ".limbi"
API_KEYS_CONFIG_KEY = "provider_api_keys"

_DEFAULT_CONFIG = {
    "version": "1.5.1",
    "created_at": "",
    "provider": "ollama",
    "model": "llama3.2:3b",
    "base_url": "http://localhost:11434",
    "temperature": 0.1,
    "max_tokens": 1024,
    "session_ttl_hours": 24,
    "auto_publish_context": True,
    API_KEYS_CONFIG_KEY: {},
}


def provider_api_key_id(provider: str, base_url: str | None = None) -> str:
    name = (provider or "").strip().lower()
    normalized_base = (base_url or "").strip().rstrip("/")
    if name in {"openai_compatible", "azure", "azure_openai"} and normalized_base:
        return f"{name}::{normalized_base}"
    return name


def _normalize_provider_api_keys(config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(config)
    keys = normalized.get(API_KEYS_CONFIG_KEY)
    if not isinstance(keys, dict):
        keys = {}

    legacy_key = str(normalized.pop("api_key", "") or "").strip()
    if legacy_key:
        key_id = provider_api_key_id(
            normalized.get("provider", ""),
            normalized.get("base_url", ""),
        )
        if key_id:
            keys[key_id] = legacy_key

    cleaned_keys = {
        str(key).strip(): str(value).strip()
        for key, value in keys.items()
        if str(key).strip() and str(value).strip()
    }
    normalized[API_KEYS_CONFIG_KEY] = cleaned_keys
    normalized["api_key_set"] = bool(cleaned_keys)
    return normalized


def get_provider_api_keys(config: dict[str, Any]) -> dict[str, str]:
    keys = config.get(API_KEYS_CONFIG_KEY)
    if not isinstance(keys, dict):
        return {}
    return {
        str(key).strip(): str(value).strip()
        for key, value in keys.items()
        if str(key).strip() and str(value).strip()
    }


def get_provider_api_key(config: dict[str, Any], provider: str, base_url: str | None = None) -> str:
    keys = get_provider_api_keys(config)
    return keys.get(provider_api_key_id(provider, base_url), "")


def set_provider_api_key(
    config: dict[str, Any],
    provider: str,
    api_key: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    normalized = dict(config)
    keys = get_provider_api_keys(normalized)
    key_id = provider_api_key_id(provider, base_url)
    if api_key.strip():
        keys[key_id] = api_key.strip()
    elif key_id in keys:
        keys.pop(key_id, None)
    normalized[API_KEYS_CONFIG_KEY] = keys
    normalized["api_key_set"] = bool(keys)
    normalized.pop("api_key", None)
    return normalized


def delete_provider_api_key(
    config: dict[str, Any],
    provider: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    return set_provider_api_key(config, provider, "", base_url=base_url)


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
            config = set_provider_api_key(
                config,
                config["provider"],
                os.getenv("LLM_API_KEY", ""),
                config["base_url"],
            )

        config_path.write_text(json.dumps(_normalize_provider_api_keys(config), indent=2) + "\n", encoding="utf-8")
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
        "LIMBI_WORKSPACE_ROOT": str(ws.parent),
        "WORKSPACE_ROOT": str(ws.parent),
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
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            normalized = _normalize_provider_api_keys(loaded)
            if normalized != loaded:
                save_config(normalized, base_dir=base_dir)
            return normalized
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read config: %s", exc)

    return dict(_DEFAULT_CONFIG)


def save_config(config: dict[str, Any], base_dir: str | None = None) -> None:
    ws = get_workspace_path(base_dir)
    config_path = ws / "config.json"
    config_path.write_text(json.dumps(_normalize_provider_api_keys(config), indent=2) + "\n", encoding="utf-8")


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
