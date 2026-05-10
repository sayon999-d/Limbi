from __future__ import annotations

import logging
import time
from typing import Any

from agents import BaseAgent, get_agent, list_agents

logger = logging.getLogger("limbi.agents.taskloop")

_LOOPS: dict[str, dict[str, Any]] = {}


class TaskLoopAgent(BaseAgent):

    agent_name = "taskloop_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "task_execution_loop",
            "status": "ready",
            "active_loops": len([l for l in _LOOPS.values() if l["status"] == "running"]),
            "total_loops": len(_LOOPS),
        }

    def handle_start_loop(
        self,
        goal: str = "",
        steps: list[dict[str, Any]] | None = None,
        max_iterations: int = 10,
        prompt: str = "",
        task: str = "",
        query: str = "",
        description: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        goal = goal or prompt or task or query or description
        if not goal:
            raise ValueError("A 'goal' is required")

        loop_id = f"loop_{int(time.time()) % 100000}"

        results: list[dict[str, Any]] = []
        if steps:
            for i, step in enumerate(steps):
                agent_name = step.get("agent", "")
                action = step.get("action", "")
                params = step.get("params", {})

                if not agent_name or not action:
                    results.append({
                        "step": i + 1,
                        "status": "skipped",
                        "reason": "Missing agent or action",
                    })
                    continue

                try:
                    agent = get_agent(agent_name)
                    result = agent.execute(action, params)
                    results.append({
                        "step": i + 1,
                        "agent": agent_name,
                        "action": action,
                        "success": result.success,
                        "message": result.data.get("message", "") if result.data else result.error,
                    })
                except Exception as exc:
                    results.append({
                        "step": i + 1,
                        "agent": agent_name,
                        "action": action,
                        "success": False,
                        "error": str(exc),
                    })
        else:
            results.append({
                "step": 1,
                "status": "pending",
                "message": f"Loop created for goal: '{goal}'. Provide 'steps' to execute.",
            })

        _LOOPS[loop_id] = {
            "id": loop_id,
            "goal": goal,
            "status": "completed" if steps else "pending",
            "steps_executed": len(results),
            "max_iterations": max_iterations,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        return {
            "message": f"Task loop '{loop_id}' {'executed' if steps else 'created'} for: {goal}",
            "loop_id": loop_id,
            "goal": goal,
            "results": results,
            "steps_executed": len(results),
            "status": _LOOPS[loop_id]["status"],
        }

    def handle_get_loop(self, loop_id: str = "", **kw: Any) -> dict[str, Any]:
        if not loop_id:
            raise ValueError("'loop_id' is required")
        loop = _LOOPS.get(loop_id)
        if not loop:
            return {"message": f"Loop '{loop_id}' not found", "found": False}
        return {"message": f"Loop '{loop_id}' details", **loop}

    def handle_list_loops(self, **kw: Any) -> dict[str, Any]:
        return {
            "message": f"Found {len(_LOOPS)} loop(s)",
            "loops": [
                {"id": l["id"], "goal": l["goal"], "status": l["status"]}
                for l in _LOOPS.values()
            ],
            "total": len(_LOOPS),
        }

    def handle_stop_loop(self, loop_id: str = "", **kw: Any) -> dict[str, Any]:
        if not loop_id:
            raise ValueError("'loop_id' is required")
        loop = _LOOPS.get(loop_id)
        if not loop:
            return {"message": f"Loop '{loop_id}' not found", "stopped": False}
        loop["status"] = "stopped"
        return {"message": f"Loop '{loop_id}' stopped", "stopped": True}
