from __future__ import annotations

from typing import Any

from . import BaseAgent
from .execution_backends import (
    build_backend_plan,
    get_execution_backend,
    list_execution_backends,
    recommend_execution_backend,
)


class ExecutionBackendAgent(BaseAgent):
    agent_name = "execution_backend_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "execution_backend",
            "status": "ready",
            "capabilities": [
                "list_backends",
                "select_backend",
                "recommend_backend",
                "build_backend_plan",
            ],
        }

    def handle_list_backends(self, **kw: Any) -> dict[str, Any]:
        return {
            "message": "Listed execution backends",
            "backends": list_execution_backends(),
        }

    def handle_select_backend(self, backend: str = "", **kw: Any) -> dict[str, Any]:
        profile = get_execution_backend(backend)
        if not profile:
            raise ValueError(f"Unknown backend '{backend}'")
        return {
            "message": f"Selected backend '{profile['name']}'",
            "backend": profile,
        }

    def handle_recommend_backend(self, task_text: str = "", **kw: Any) -> dict[str, Any]:
        return {
            "message": "Recommended backend",
            "backend": recommend_execution_backend(task_text),
        }

    def handle_build_backend_plan(self, task_text: str = "", backend: str = "", **kw: Any) -> dict[str, Any]:
        return build_backend_plan(task_text, backend_name=backend)

