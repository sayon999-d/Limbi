from __future__ import annotations

from importlib import import_module
from typing import Any

__version__ = "1.8.2"
__author__ = "Sayon Manna"

from limbi.agents import BaseAgent, AgentResult, get_agent, list_agents

_LAZY_EXPORTS = {
    "Orchestrator": ("limbi.orchestrator", "Orchestrator"),
    "get_llm_provider": ("limbi.llm_provider", "get_llm_provider"),
    "list_providers": ("limbi.llm_provider", "list_providers"),
    "ProviderConfig": ("limbi.llm_provider", "ProviderConfig"),
    "init_db": ("limbi.audit_log", "init_db"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_name, attribute_name = _LAZY_EXPORTS[name]
        module = import_module(module_name)
        value = getattr(module, attribute_name)
        globals()[name] = value
        return value

    if name.endswith("_agent"):
        module = import_module(f"limbi.agents.{name}")
        globals()[name] = module
        return module

    raise AttributeError(f"module 'limbi' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(
        set(
            [
                "__version__",
                "__author__",
                "BaseAgent",
                "AgentResult",
                "get_agent",
                "list_agents",
                *list(_LAZY_EXPORTS.keys()),
            ]
        )
    )


__all__ = [
    "__version__",
    "__author__",
    "BaseAgent",
    "AgentResult",
    "get_agent",
    "list_agents",
    "Orchestrator",
    "get_llm_provider",
    "list_providers",
    "ProviderConfig",
    "init_db",
]
