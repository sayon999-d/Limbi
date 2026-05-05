

from __future__ import annotations

import logging
import time
from typing import Any

from . import BaseAgent, get_agent, list_agents

logger = logging.getLogger("limbi.agents.swarm")

class SwarmAgent(BaseAgent):

    agent_name = "swarm_agent"

    def health_check(self) -> dict[str, Any]:
        all_agents = list_agents()
        return {
            "agent": self.agent_name,
            "type": "swarm_orchestration",
            "status": "ready",
            "managed_agents": len(all_agents),
            "agent_names": list(all_agents.keys()),
            "capabilities": [
                "ensemble", "pipeline", "vote",
                "broadcast", "health_check_all",
            ],
        }

    def handle_ensemble(
        self,
        agents_actions: list[dict[str, Any]] | None = None,
        merge_strategy: str = "collect",
        **kw: Any,
    ) -> dict[str, Any]:

        if not agents_actions:
            raise ValueError("'agents_actions' list is required")

        results: list[dict[str, Any]] = []
        errors: list[str] = []

        for spec in agents_actions:
            agent_name = spec.get("agent", "")
            action = spec.get("action", "")
            params = spec.get("params", {})

            start = time.time()
            try:
                agent = get_agent(agent_name)
                result = agent.execute(action, params)
                elapsed = (time.time() - start) * 1000

                results.append({
                    "agent": agent_name,
                    "action": action,
                    "success": result.success,
                    "data": result.data,
                    "error": result.error,
                    "time_ms": round(elapsed, 1),
                })
            except Exception as exc:
                errors.append(f"{agent_name}.{action}: {exc}")
                results.append({
                    "agent": agent_name,
                    "action": action,
                    "success": False,
                    "error": str(exc),
                    "time_ms": round((time.time() - start) * 1000, 1),
                })

        successful = [r for r in results if r["success"]]
        merged: Any = None

        if merge_strategy == "collect":
            merged = results
        elif merge_strategy == "best":

            if successful:
                merged = max(successful, key=lambda r: len(str(r.get("data", ""))))
        elif merge_strategy == "vote":

            merged = {"majority_success": len(successful) > len(results) / 2}

        return {
            "message": f"Ensemble: {len(successful)}/{len(results)} agents succeeded",
            "strategy": merge_strategy,
            "total_agents": len(results),
            "successful": len(successful),
            "failed": len(results) - len(successful),
            "merged_result": merged,
            "errors": errors,
            "total_time_ms": round(sum(r.get("time_ms", 0) for r in results), 1),
        }

    def handle_pipeline(
        self,
        steps: list[dict[str, Any]] | None = None,
        stop_on_error: bool = True,
        **kw: Any,
    ) -> dict[str, Any]:

        if not steps:
            raise ValueError("'steps' list is required for pipeline")

        pipeline_results: list[dict[str, Any]] = []
        previous_data: dict[str, Any] = {}
        pipeline_start = time.time()

        for i, step in enumerate(steps):
            agent_name = step.get("agent", "")
            action = step.get("action", "")
            params = dict(step.get("params", {}))

            pass_as = step.get("pass_result_as", "")
            if pass_as and previous_data:
                params[pass_as] = previous_data

            start = time.time()
            try:
                agent = get_agent(agent_name)
                result = agent.execute(action, params)
                elapsed = (time.time() - start) * 1000

                step_result = {
                    "step": i + 1,
                    "agent": agent_name,
                    "action": action,
                    "success": result.success,
                    "data": result.data,
                    "error": result.error,
                    "time_ms": round(elapsed, 1),
                }

                pipeline_results.append(step_result)

                if result.success:
                    previous_data = result.data
                elif stop_on_error:
                    break

            except Exception as exc:
                pipeline_results.append({
                    "step": i + 1,
                    "agent": agent_name,
                    "action": action,
                    "success": False,
                    "error": str(exc),
                    "time_ms": round((time.time() - start) * 1000, 1),
                })
                if stop_on_error:
                    break

        completed = len(pipeline_results)
        successful = sum(1 for r in pipeline_results if r["success"])

        return {
            "message": f"Pipeline: {successful}/{completed} steps completed (of {len(steps)} total)",
            "total_steps": len(steps),
            "completed_steps": completed,
            "successful_steps": successful,
            "steps": pipeline_results,
            "final_output": previous_data,
            "total_time_ms": round((time.time() - pipeline_start) * 1000, 1),
            "status": "completed" if completed == len(steps) and successful == completed else "partial",
        }

    def handle_vote(
        self,
        query: str = "",
        voter_agents: list[dict[str, Any]] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        if not voter_agents:
            raise ValueError("'voter_agents' list is required")

        votes: list[dict[str, Any]] = []

        for spec in voter_agents:
            agent_name = spec.get("agent", "")
            action = spec.get("action", "")
            params = spec.get("params", {})

            try:
                agent = get_agent(agent_name)
                result = agent.execute(action, params)
                votes.append({
                    "agent": agent_name,
                    "vote": "approve" if result.success else "reject",
                    "confidence": 1.0 if result.success else 0.0,
                    "reasoning": result.data.get("message", str(result.data)[:100]),
                })
            except Exception as exc:
                votes.append({
                    "agent": agent_name,
                    "vote": "abstain",
                    "confidence": 0.0,
                    "reasoning": f"Error: {exc}",
                })

        approve = sum(1 for v in votes if v["vote"] == "approve")
        reject = sum(1 for v in votes if v["vote"] == "reject")
        abstain = sum(1 for v in votes if v["vote"] == "abstain")

        verdict = "approved" if approve > reject else "rejected" if reject > approve else "tie"

        return {
            "message": f"Vote result: {verdict} ({approve} approve, {reject} reject, {abstain} abstain)",
            "query": query,
            "verdict": verdict,
            "tally": {"approve": approve, "reject": reject, "abstain": abstain},
            "votes": votes,
            "quorum_met": (approve + reject) >= len(voter_agents) * 0.5,
        }

    def handle_broadcast(
        self,
        action: str = "health_check",
        params: dict[str, Any] | None = None,
        agent_filter: list[str] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        all_agents = list_agents()

        if agent_filter:
            target_agents = {k: v for k, v in all_agents.items() if k in agent_filter}
        else:
            target_agents = all_agents

        results: dict[str, Any] = {}
        for name in target_agents:
            if name == self.agent_name:
                continue

            try:
                agent = get_agent(name)
                if action == "health_check":
                    results[name] = agent.health_check()
                else:
                    result = agent.execute(action, params or {})
                    results[name] = result.to_dict()
            except Exception as exc:
                results[name] = {"error": str(exc)}

        return {
            "message": f"Broadcast '{action}' to {len(results)} agents",
            "action": action,
            "total_agents": len(results),
            "results": results,
        }

    def handle_health_check_all(self, **kw: Any) -> dict[str, Any]:

        return self.handle_broadcast(action="health_check")
