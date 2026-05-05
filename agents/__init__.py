from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

logger = logging.getLogger("limbi.agents")

@dataclass
class AgentResult:

    success: bool
    agent: str
    action: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "agent": self.agent,
            "action": self.action,
            "data": self.data,
            "error": self.error,
        }

class BaseAgent(ABC):

    agent_name: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.agent_name:
            _AGENT_REGISTRY[cls.agent_name] = cls
            logger.info("Registered agent: %s -> %s", cls.agent_name, cls.__name__)

    def execute(self, action: str, params: dict[str, Any] | None = None) -> AgentResult:
        handler = getattr(self, f"handle_{action}", None)
        if handler is None:
            return AgentResult(
                success=False,
                agent=self.agent_name,
                action=action,
                error=f"Unknown action '{action}' for agent '{self.agent_name}'. "
                      f"Available: {self.available_actions}",
            )
        try:
            data = handler(**(params or {}))
            return AgentResult(success=True, agent=self.agent_name, action=action, data=data)
        except Exception as exc:
            logger.exception("Agent %s action %s failed", self.agent_name, action)
            return AgentResult(
                success=False,
                agent=self.agent_name,
                action=action,
                error="Agent execution failed",
            )

    @property
    def available_actions(self) -> list[str]:
        return [
            m.removeprefix("handle_")
            for m in dir(self)
            if m.startswith("handle_") and callable(getattr(self, m))
        ]

    @abstractmethod
    def health_check(self) -> dict[str, Any]:

        ...

_AGENT_REGISTRY: dict[str, type[BaseAgent]] = {}

def get_agent(name: str) -> BaseAgent:
    cls = _AGENT_REGISTRY.get(name)
    if cls is None:
        raise KeyError(
            f"No agent registered as '{name}'. "
            f"Known agents: {list(_AGENT_REGISTRY)}"
        )
    return cls()

def list_agents() -> dict[str, list[str]]:
    return {
        name: cls().available_actions
        for name, cls in _AGENT_REGISTRY.items()
    }
