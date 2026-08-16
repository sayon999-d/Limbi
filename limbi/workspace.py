
from __future__ import annotations

import json
import logging
import os
import time
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("limbi.workspace")

WORKSPACE_DIR_NAME = ".limbi"
SKILL_HUB_DIR_NAME = "skill_hub"
AGENT_GUIDE_FILENAMES = ("agent.md", ".limbi/agent.md")
API_KEYS_CONFIG_KEY = "provider_api_keys"
PREFERRED_MODELS_CONFIG_KEY = "preferred_models"
CUSTOM_SKILLS_CONFIG_KEY = "custom_skills"
CUSTOM_MCP_SERVERS_CONFIG_KEY = "custom_mcp_servers"
CUSTOM_MCP_PLUGINS_CONFIG_KEY = "custom_mcp_plugins"
PERMISSIONS_CONFIG_KEY = "permissions"

_DEFAULT_PERMISSION_POLICY = {
    "network": {
        "default": "allow",
        "research_agent": "allow",
        "browser_agent": "allow",
        "web_scraping_agent": "allow",
    },
    "filesystem": {
        "default": "workspace_only",
        "file_agent": "workspace_only",
    },
    "agent_scopes": {
        "default": "allow",
        "mutation_agent": "approval_required",
    },
}

_DEFAULT_CONFIG = {
    "version": "1.6.2",
    "created_at": "",
    "provider": "ollama",
    "model": "llama3.2:3b",
    "base_url": "http://localhost:11434",
    "temperature": 0.1,
    "max_tokens": 768,
    "session_ttl_hours": 24,
    "auto_publish_context": True,
    API_KEYS_CONFIG_KEY: {},
    PREFERRED_MODELS_CONFIG_KEY: {},
    CUSTOM_SKILLS_CONFIG_KEY: {},
    CUSTOM_MCP_SERVERS_CONFIG_KEY: {},
    CUSTOM_MCP_PLUGINS_CONFIG_KEY: {},
    PERMISSIONS_CONFIG_KEY: _DEFAULT_PERMISSION_POLICY,
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


def _normalize_preferred_models(config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(config)
    preferred = normalized.get(PREFERRED_MODELS_CONFIG_KEY)
    if not isinstance(preferred, dict):
        preferred = {}

    cleaned: dict[str, str] = {}
    for key, value in preferred.items():
        cleaned_key = str(key).strip().lower()
        cleaned_value = str(value).strip()
        if cleaned_key and cleaned_value:
            cleaned[cleaned_key] = cleaned_value
    normalized[PREFERRED_MODELS_CONFIG_KEY] = cleaned
    return normalized


def _normalize_custom_skills(config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(config)
    skills = normalized.get(CUSTOM_SKILLS_CONFIG_KEY)
    if not isinstance(skills, dict):
        skills = {}

    cleaned: dict[str, dict[str, Any]] = {}
    for raw_name, raw_skill in skills.items():
        name = str(raw_name).strip().lower().replace(" ", "-")
        if not name:
            continue
        skill = raw_skill if isinstance(raw_skill, dict) else {"instruction": str(raw_skill)}
        cleaned[name] = {
            "name": name,
            "description": str(skill.get("description", "")).strip(),
            "instruction": str(skill.get("instruction", "")).strip(),
            "provider": str(skill.get("provider", "")).strip(),
            "model": str(skill.get("model", "")).strip(),
            "base_url": str(skill.get("base_url", "")).strip(),
            "version": str(skill.get("version", "")).strip() or "1.0.0",
            "created_at": str(skill.get("created_at", "")).strip(),
            "updated_at": str(skill.get("updated_at", "")).strip(),
            "examples": list(skill.get("examples", []) or []),
            "capabilities": list(skill.get("capabilities", []) or []),
            "tags": list(skill.get("tags", []) or []),
            "source": str(skill.get("source", "")).strip(),
            "standard": str(skill.get("standard", "")).strip(),
            "self_improving": bool(skill.get("self_improving", False)),
            "last_refined_at": str(skill.get("last_refined_at", "")).strip(),
            "evaluation_notes": str(skill.get("evaluation_notes", "")).strip(),
            "hub_url": str(skill.get("hub_url", "")).strip(),
        }
    normalized[CUSTOM_SKILLS_CONFIG_KEY] = cleaned
    return normalized


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            cleaned.append(text)
    return cleaned


def _normalize_env_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key).strip(): str(item).strip()
        for key, item in value.items()
        if str(key).strip() and str(item).strip()
    }


def _normalize_mcp_server(name: str, server: Any, *, source: str = "", plugin: str = "") -> dict[str, Any]:
    payload = server if isinstance(server, dict) else {}
    normalized_name = str(name or payload.get("name") or "").strip()
    if not normalized_name:
        return {}

    server_type = str(payload.get("type") or "").strip().lower()
    command = str(payload.get("command") or "").strip()
    url = str(payload.get("url") or "").strip()
    if not server_type:
        server_type = "stdio" if command else "sse" if url else "stdio"

    args = payload.get("args")
    if not isinstance(args, list):
        args = []

    cleaned: dict[str, Any] = {
        "name": normalized_name,
        "type": server_type,
        "description": str(payload.get("description") or "").strip(),
        "enabled": bool(payload.get("enabled", True)),
        "command": command,
        "args": _normalize_string_list(args),
        "env": _normalize_env_map(payload.get("env")),
        "url": url,
        "cwd": str(payload.get("cwd") or "").strip(),
        "source": str(payload.get("source") or source).strip(),
        "plugin": str(payload.get("plugin") or plugin).strip(),
    }

    # Preserve any extra fields users may want to pass through to mcp.json.
    for key, value in payload.items():
        if key in cleaned or key in {"args", "env"}:
            continue
        if value is None:
            continue
        cleaned[key] = value

    # Drop empty values that would only add noise to generated configs.
    return {key: value for key, value in cleaned.items() if value not in ("", [], {}, None) or key in {"enabled", "args", "env"}}


def _normalize_mcp_server_collection(
    value: Any,
    *,
    source: str = "",
    plugin: str = "",
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, dict[str, Any]] = {}
    for raw_name, raw_server in value.items():
        server = _normalize_mcp_server(str(raw_name), raw_server, source=source, plugin=plugin)
        if server:
            cleaned[server["name"]] = server
    return cleaned


def _normalize_custom_mcp_servers(config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(config)
    servers = normalized.get(CUSTOM_MCP_SERVERS_CONFIG_KEY)
    if not isinstance(servers, dict):
        servers = {}
    normalized[CUSTOM_MCP_SERVERS_CONFIG_KEY] = _normalize_mcp_server_collection(servers, source="workspace")
    return normalized


def _normalize_custom_mcp_plugins(config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(config)
    plugins = normalized.get(CUSTOM_MCP_PLUGINS_CONFIG_KEY)
    if not isinstance(plugins, dict):
        plugins = {}

    cleaned: dict[str, dict[str, Any]] = {}
    for raw_name, raw_plugin in plugins.items():
        plugin = raw_plugin if isinstance(raw_plugin, dict) else {}
        name = str(raw_name or plugin.get("name") or "").strip().lower().replace(" ", "-")
        if not name:
            continue

        servers = plugin.get("servers")
        if isinstance(servers, list):
            server_map = {}
            for idx, item in enumerate(servers):
                item_name = str((item or {}).get("name") or f"server-{idx+1}").strip()
                server_map[item_name] = item
        else:
            server_map = servers if isinstance(servers, dict) else {}

        cleaned[name] = {
            "name": name,
            "description": str(plugin.get("description", "")).strip(),
            "version": str(plugin.get("version", "")).strip() or "1.0.0",
            "enabled": bool(plugin.get("enabled", True)),
            "source": str(plugin.get("source", "")).strip(),
            "servers": _normalize_mcp_server_collection(server_map, source="plugin", plugin=name),
            "tags": _normalize_string_list(plugin.get("tags")),
            "env": _normalize_env_map(plugin.get("env")),
            "metadata": plugin.get("metadata") if isinstance(plugin.get("metadata"), dict) else {},
        }

        for key, value in plugin.items():
            if key in cleaned[name] or key in {"servers", "tags", "env", "metadata"}:
                continue
            if value is None:
                continue
            cleaned[name][key] = value

    normalized[CUSTOM_MCP_PLUGINS_CONFIG_KEY] = cleaned
    return normalized


def _normalize_permissions(config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(config)
    policy = normalized.get(PERMISSIONS_CONFIG_KEY)
    if not isinstance(policy, dict):
        policy = {}

    cleaned: dict[str, dict[str, str]] = {}
    for scope, entries in _DEFAULT_PERMISSION_POLICY.items():
        scope_entries = policy.get(scope)
        if not isinstance(scope_entries, dict):
            scope_entries = {}
        merged: dict[str, str] = {str(k).strip().lower(): str(v).strip().lower() for k, v in entries.items()}
        for key, value in scope_entries.items():
            cleaned_key = str(key).strip().lower()
            cleaned_value = str(value).strip().lower()
            if cleaned_key and cleaned_value:
                merged[cleaned_key] = cleaned_value
        cleaned[scope] = merged

    for scope, entries in policy.items():
        if scope in cleaned or not isinstance(entries, dict):
            continue
        cleaned[scope] = {
            str(key).strip().lower(): str(value).strip().lower()
            for key, value in entries.items()
            if str(key).strip() and str(value).strip()
        }

    normalized[PERMISSIONS_CONFIG_KEY] = cleaned
    return _normalize_preferred_models(normalized)


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


def preferred_model_id(provider: str, base_url: str | None = None) -> str:
    name = (provider or "").strip().lower()
    normalized_base = (base_url or "").strip().rstrip("/")
    if name in {"openai_compatible", "azure", "azure_openai"} and normalized_base:
        return f"{name}::{normalized_base}"
    return name


def get_preferred_model(config: dict[str, Any], provider: str, base_url: str | None = None) -> str:
    models = config.get(PREFERRED_MODELS_CONFIG_KEY)
    if not isinstance(models, dict):
        return ""
    return str(models.get(preferred_model_id(provider, base_url), "")).strip()


def set_preferred_model(
    config: dict[str, Any],
    provider: str,
    model: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    normalized = dict(config)
    models = normalized.get(PREFERRED_MODELS_CONFIG_KEY)
    if not isinstance(models, dict):
        models = {}
    key = preferred_model_id(provider, base_url)
    cleaned_model = str(model or "").strip()
    if cleaned_model:
        models[key] = cleaned_model
    elif key in models:
        models.pop(key, None)
    normalized[PREFERRED_MODELS_CONFIG_KEY] = models
    return _normalize_preferred_models(normalized)


def get_workspace_path(base_dir: str | None = None) -> Path:
    base = Path(base_dir).expanduser().resolve() if base_dir else Path.cwd().resolve()
    return base / WORKSPACE_DIR_NAME


def get_workspace_root(base_dir: str | None = None) -> Path:
    return get_workspace_path(base_dir).parent


def resolve_agent_guide_path(base_dir: str | None = None) -> Path | None:
    root = get_workspace_root(base_dir)
    workspace = get_workspace_path(base_dir)
    for candidate in (root / AGENT_GUIDE_FILENAMES[0], workspace / "agent.md"):
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def load_agent_guide_text(base_dir: str | None = None, max_chars: int = 6000) -> str:
    guide_path = resolve_agent_guide_path(base_dir)
    if not guide_path:
        return ""
    try:
        text = guide_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return ""
    if max_chars > 0 and len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 3].rstrip() + "..."
    return cleaned


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
        ws / SKILL_HUB_DIR_NAME,
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

        config_path.write_text(
            json.dumps(
                _normalize_permissions(
                    _normalize_custom_mcp_plugins(
                        _normalize_custom_mcp_servers(
                            _normalize_custom_skills(_normalize_provider_api_keys(config))
                        )
                    )
                ),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
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
        os.environ[key] = path


def load_config(base_dir: str | None = None) -> dict[str, Any]:
    ws = get_workspace_path(base_dir)
    config_path = ws / "config.json"

    if config_path.exists():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            normalized = _normalize_permissions(
                _normalize_custom_mcp_plugins(
                    _normalize_custom_mcp_servers(
                        _normalize_custom_skills(_normalize_provider_api_keys(loaded))
                    )
                )
            )
            if normalized != loaded:
                save_config(normalized, base_dir=base_dir)
            return normalized
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read config: %s", exc)

    return dict(_DEFAULT_CONFIG)


def save_config(config: dict[str, Any], base_dir: str | None = None) -> None:
    ws = get_workspace_path(base_dir)
    config_path = ws / "config.json"
    config_path.write_text(
        json.dumps(
            _normalize_permissions(
                _normalize_custom_mcp_plugins(
                    _normalize_custom_mcp_servers(
                        _normalize_custom_skills(_normalize_provider_api_keys(config))
                    )
                )
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def get_permission_policy(config: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_permissions(config)
    policy = normalized.get(PERMISSIONS_CONFIG_KEY)
    return policy if isinstance(policy, dict) else {}


def set_permission_policy(
    config: dict[str, Any],
    scope: str,
    actor: str,
    mode: str,
) -> dict[str, Any]:
    normalized = dict(config)
    policy = get_permission_policy(normalized)
    scope_key = str(scope or "").strip().lower()
    actor_key = str(actor or "").strip().lower()
    mode_key = str(mode or "").strip().lower()
    if not scope_key or not actor_key or not mode_key:
        return normalized
    scope_policy = dict(policy.get(scope_key, {}))
    scope_policy[actor_key] = mode_key
    policy[scope_key] = scope_policy
    normalized[PERMISSIONS_CONFIG_KEY] = policy
    return _normalize_permissions(normalized)


def is_permission_allowed(
    config: dict[str, Any],
    scope: str,
    actor: str,
    action: str = "",
) -> bool:
    from .permissions import evaluate_permission

    return evaluate_permission(config, scope, actor, action).allowed


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


def get_custom_skills(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    skills = config.get(CUSTOM_SKILLS_CONFIG_KEY)
    if not isinstance(skills, dict):
        return {}
    normalized = _normalize_custom_skills({CUSTOM_SKILLS_CONFIG_KEY: skills})
    return normalized.get(CUSTOM_SKILLS_CONFIG_KEY, {})


def get_custom_skill(config: dict[str, Any], name: str) -> dict[str, Any]:
    skills = get_custom_skills(config)
    return dict(skills.get(str(name).strip().lower().replace(" ", "-"), {}))


def set_custom_skill(
    config: dict[str, Any],
    name: str,
    skill: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(config)
    skills = get_custom_skills(normalized)
    skill_name = str(name).strip().lower().replace(" ", "-")
    if not skill_name:
        return normalized
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    skills[skill_name] = {
        "name": skill_name,
        "description": str(skill.get("description", "")).strip(),
        "instruction": str(skill.get("instruction", "")).strip(),
        "provider": str(skill.get("provider", "")).strip(),
        "model": str(skill.get("model", "")).strip(),
        "base_url": str(skill.get("base_url", "")).strip(),
        "version": str(skill.get("version", "")).strip() or "1.0.0",
        "created_at": str(skill.get("created_at", "")).strip() or now,
        "updated_at": now,
        "examples": list(skill.get("examples", []) or []),
        "capabilities": list(skill.get("capabilities", []) or []),
        "tags": list(skill.get("tags", []) or []),
        "source": str(skill.get("source", "")).strip(),
        "standard": str(skill.get("standard", "")).strip(),
        "self_improving": bool(skill.get("self_improving", False)),
        "last_refined_at": str(skill.get("last_refined_at", "")).strip(),
        "evaluation_notes": str(skill.get("evaluation_notes", "")).strip(),
        "hub_url": str(skill.get("hub_url", "")).strip(),
    }
    normalized[CUSTOM_SKILLS_CONFIG_KEY] = skills
    return normalized


def delete_custom_skill(config: dict[str, Any], name: str) -> dict[str, Any]:
    normalized = dict(config)
    skills = get_custom_skills(normalized)
    skill_name = str(name).strip().lower().replace(" ", "-")
    skills.pop(skill_name, None)
    normalized[CUSTOM_SKILLS_CONFIG_KEY] = skills
    return normalized


def export_custom_skill(config: dict[str, Any], name: str) -> dict[str, Any]:
    skill = get_custom_skill(config, name)
    if not skill:
        return {}
    export = dict(skill)
    export["exported_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return export


def export_custom_skill_pack(config: dict[str, Any], name: str) -> dict[str, Any]:
    skill = get_custom_skill(config, name)
    if not skill:
        return {}
    exported_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "format": "limbi-skill-pack",
        "exported_at": exported_at,
        "manifest": {
            "name": skill.get("name", name),
            "version": skill.get("version", "1.0.0"),
            "provider": skill.get("provider", ""),
            "model": skill.get("model", ""),
            "base_url": skill.get("base_url", ""),
            "description": skill.get("description", ""),
        },
        "skill": dict(skill),
    }


def import_custom_skill(
    config: dict[str, Any],
    skill: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(config)
    skill_name = str(skill.get("name") or skill.get("skill_name") or "").strip()
    if not skill_name:
        raise ValueError("Imported skill requires a name")
    return set_custom_skill(normalized, skill_name, skill)


def import_custom_skill_pack(
    config: dict[str, Any],
    pack: dict[str, Any],
) -> dict[str, Any]:
    skill = pack.get("skill") if isinstance(pack, dict) else None
    if not isinstance(skill, dict):
        skill = pack if isinstance(pack, dict) else {}
    if not skill:
        raise ValueError("Imported skill pack requires a skill payload")
    return import_custom_skill(config, skill)


def get_skill_hub_path(base_dir: str | None = None) -> Path:
    return get_workspace_path(base_dir) / SKILL_HUB_DIR_NAME


def publish_skill_pack(
    config: dict[str, Any],
    name: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    skill = get_custom_skill(config, name)
    if not skill:
        raise ValueError(f"No custom skill named '{name}'")
    ws = get_workspace_path()
    hub = get_skill_hub_path()
    hub.mkdir(parents=True, exist_ok=True)
    published_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    pack = {
        "format": "limbi-skill-pack",
        "published_at": published_at,
        "metadata": metadata or {},
        "manifest": {
            "name": skill.get("name", name),
            "version": skill.get("version", "1.0.0"),
            "provider": skill.get("provider", ""),
            "model": skill.get("model", ""),
            "base_url": skill.get("base_url", ""),
            "description": skill.get("description", ""),
            "standard": skill.get("standard", "agentskills.io-compatible"),
        },
        "skill": dict(skill),
        "workspace": str(ws),
    }
    file_name = f"{skill.get('name', name)}-{skill.get('version', '1.0.0')}.json"
    pack_path = hub / file_name
    pack_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "message": f"Published skill pack '{skill.get('name', name)}'",
        "pack_path": str(pack_path),
        "pack": pack,
    }


def list_skill_hub(base_dir: str | None = None) -> list[dict[str, Any]]:
    hub = get_skill_hub_path(base_dir)
    if not hub.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(hub.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {}
            items.append(
                {
                    "path": str(path),
                    "name": str((manifest or {}).get("name") or path.stem),
                    "version": str((manifest or {}).get("version") or ""),
                    "provider": str((manifest or {}).get("provider") or ""),
                    "model": str((manifest or {}).get("model") or ""),
                    "description": str((manifest or {}).get("description") or ""),
                    "published_at": str(payload.get("published_at") or ""),
                }
            )
    return items


def get_custom_mcp_servers(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    servers = config.get(CUSTOM_MCP_SERVERS_CONFIG_KEY)
    if not isinstance(servers, dict):
        return {}
    normalized = _normalize_custom_mcp_servers({CUSTOM_MCP_SERVERS_CONFIG_KEY: servers})
    return normalized.get(CUSTOM_MCP_SERVERS_CONFIG_KEY, {})


def get_custom_mcp_server(config: dict[str, Any], name: str) -> dict[str, Any]:
    servers = get_custom_mcp_servers(config)
    return dict(servers.get(str(name).strip().lower().replace(" ", "-"), {}))


def set_custom_mcp_server(
    config: dict[str, Any],
    name: str,
    server: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(config)
    servers = get_custom_mcp_servers(normalized)
    server_name = str(name).strip().lower().replace(" ", "-")
    if not server_name:
        return normalized
    payload = dict(server)
    payload["name"] = server_name
    servers[server_name] = _normalize_mcp_server(server_name, payload, source="workspace")
    normalized[CUSTOM_MCP_SERVERS_CONFIG_KEY] = servers
    return _normalize_custom_mcp_servers(normalized)


def delete_custom_mcp_server(config: dict[str, Any], name: str) -> dict[str, Any]:
    normalized = dict(config)
    servers = get_custom_mcp_servers(normalized)
    server_name = str(name).strip().lower().replace(" ", "-")
    servers.pop(server_name, None)
    normalized[CUSTOM_MCP_SERVERS_CONFIG_KEY] = servers
    return normalized


def get_custom_mcp_plugins(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    plugins = config.get(CUSTOM_MCP_PLUGINS_CONFIG_KEY)
    if not isinstance(plugins, dict):
        return {}
    normalized = _normalize_custom_mcp_plugins({CUSTOM_MCP_PLUGINS_CONFIG_KEY: plugins})
    return normalized.get(CUSTOM_MCP_PLUGINS_CONFIG_KEY, {})


def get_custom_mcp_plugin(config: dict[str, Any], name: str) -> dict[str, Any]:
    plugins = get_custom_mcp_plugins(config)
    return dict(plugins.get(str(name).strip().lower().replace(" ", "-"), {}))


def set_custom_mcp_plugin(
    config: dict[str, Any],
    name: str,
    plugin: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(config)
    plugins = get_custom_mcp_plugins(normalized)
    plugin_name = str(name).strip().lower().replace(" ", "-")
    if not plugin_name:
        return normalized
    payload = dict(plugin)
    payload["name"] = plugin_name
    plugins[plugin_name] = _normalize_custom_mcp_plugins({CUSTOM_MCP_PLUGINS_CONFIG_KEY: {plugin_name: payload}})[CUSTOM_MCP_PLUGINS_CONFIG_KEY][plugin_name]
    normalized[CUSTOM_MCP_PLUGINS_CONFIG_KEY] = plugins
    return _normalize_custom_mcp_plugins(normalized)


def delete_custom_mcp_plugin(config: dict[str, Any], name: str) -> dict[str, Any]:
    normalized = dict(config)
    plugins = get_custom_mcp_plugins(normalized)
    plugin_name = str(name).strip().lower().replace(" ", "-")
    plugins.pop(plugin_name, None)
    normalized[CUSTOM_MCP_PLUGINS_CONFIG_KEY] = plugins
    return normalized


def _dedupe_mcp_server_name(existing: dict[str, Any], name: str, source_prefix: str = "") -> str:
    base = str(name or "").strip()
    if source_prefix:
        base = f"{source_prefix}__{base}"
    candidate = base
    index = 2
    while candidate in existing:
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def resolve_mcp_servers(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    resolved: dict[str, dict[str, Any]] = {}

    def add_server(
        server_name: str,
        server: dict[str, Any],
        *,
        source_prefix: str = "",
        extra_env: dict[str, Any] | None = None,
    ) -> None:
        if not server or not bool(server.get("enabled", True)):
            return
        resolved_name = _dedupe_mcp_server_name(resolved, server_name, source_prefix=source_prefix)
        payload = dict(server)
        merged_env = dict(extra_env or {})
        merged_env.update(payload.get("env") if isinstance(payload.get("env"), dict) else {})
        if merged_env:
            payload["env"] = merged_env
        payload.pop("name", None)
        payload.pop("source", None)
        payload.pop("plugin", None)
        payload.pop("enabled", None)
        payload.pop("metadata", None)
        payload.pop("tags", None)
        payload.pop("version", None)
        if payload.get("args") == []:
            payload.pop("args", None)
        if payload.get("env") == {}:
            payload.pop("env", None)
        if payload.get("cwd") == "":
            payload.pop("cwd", None)
        if payload.get("description") == "":
            payload.pop("description", None)
        if payload.get("command") == "":
            payload.pop("command", None)
        if payload.get("url") == "":
            payload.pop("url", None)
        resolved[resolved_name] = payload

    # The packaged Limbi MCP server is always available.
    add_server(
        "limbi",
        {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "limbi.mcp_server"],
            "description": "Limbi agent and orchestration server",
            "enabled": True,
            "source": "packaged",
        },
    )

    for name, server in sorted(get_custom_mcp_servers(config).items()):
        add_server(name, server, source_prefix="")

    for plugin_name, plugin in sorted(get_custom_mcp_plugins(config).items()):
        if not plugin.get("enabled", True):
            continue
        plugin_servers = plugin.get("servers", {})
        if not isinstance(plugin_servers, dict):
            continue
        for server_name, server in sorted(plugin_servers.items()):
            add_server(
                server_name,
                server,
                source_prefix=plugin_name,
                extra_env=plugin.get("env") if isinstance(plugin.get("env"), dict) else {},
            )

    return resolved


def merge_mcp_config(
    existing_config: dict[str, Any] | None,
    workspace_config: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(existing_config) if isinstance(existing_config, dict) else {}
    existing_servers = merged.get("servers")
    if not isinstance(existing_servers, dict):
        existing_servers = {}

    merged_servers = dict(existing_servers)
    merged_servers.update(resolve_mcp_servers(workspace_config))
    merged["servers"] = merged_servers
    return merged


def build_mcp_config(
    config: dict[str, Any],
    existing_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return merge_mcp_config(existing_config, config)
