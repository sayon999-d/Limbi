from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from limbi.agent_contracts import (
    ActionContract,
    build_action_contract,
    validate_action_params,
)
from limbi.tracing import record_trace_event

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

    def action_contract(self, action: str) -> ActionContract | None:
        handler = getattr(self, f"handle_{action}", None)
        if handler is None:
            return None
        return build_action_contract(self.agent_name, action, handler)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.agent_name:
            _AGENT_REGISTRY[cls.agent_name] = cls
            logger.info("Registered agent: %s -> %s", cls.agent_name, cls.__name__)

    def execute(self, action: str, params: dict[str, Any] | None = None) -> AgentResult:
        handler = getattr(self, f"handle_{action}", None)
        if handler is None:
            record_trace_event(
                kind="agent.execute",
                agent=self.agent_name,
                action=action,
                message="unknown action",
                payload={"params": params or {}},
                status="error",
            )
            return AgentResult(
                success=False,
                agent=self.agent_name,
                action=action,
                error=f"Unknown action '{action}' for agent '{self.agent_name}'. "
                      f"Available: {self.available_actions}",
            )
        try:
            cleaned_params, validation_errors = validate_action_params(handler, params or {})
            if validation_errors:
                error_text = "; ".join(validation_errors)
                record_trace_event(
                    kind="agent.execute",
                    agent=self.agent_name,
                    action=action,
                    message="validation failed",
                    payload={"params": params or {}, "validation_errors": validation_errors},
                    status="error",
                )
                return AgentResult(
                    success=False,
                    agent=self.agent_name,
                    action=action,
                    error=f"Validation error: {error_text}",
                )
            record_trace_event(
                kind="agent.execute",
                agent=self.agent_name,
                action=action,
                message="start",
                payload={"params": cleaned_params},
                status="running",
            )
            data = handler(**cleaned_params)
            record_trace_event(
                kind="agent.execute",
                agent=self.agent_name,
                action=action,
                message="success",
                payload={"result": data},
                status="success",
            )
            return AgentResult(success=True, agent=self.agent_name, action=action, data=data)
        except Exception as exc:
            logger.exception("Agent %s action %s failed", self.agent_name, action)
            record_trace_event(
                kind="agent.execute",
                agent=self.agent_name,
                action=action,
                message="exception",
                payload={"error": f"{type(exc).__name__}: {exc}"},
                status="error",
            )
            return AgentResult(
                success=False,
                agent=self.agent_name,
                action=action,
                error=f"{type(exc).__name__}: {exc}",
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
