

from __future__ import annotations

from typing import Any

from . import BaseAgent

class WorkflowAgent(BaseAgent):

    agent_name = "workflow_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "workflow",
            "status": "ready",
            "capabilities": [
                "create_workflow",
                "validate_workflow",
                "workflow_to_pipeline",
                "estimate_workflow",
                "visualize_workflow",
            ],
        }

    def handle_create_workflow(self, name: str = "", stages: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        if not name:
            raise ValueError("'name' is required")
        stages = stages or ["intake", "analysis", "execution", "review"]
        workflow = [{"step": idx + 1, "name": stage} for idx, stage in enumerate(stages)]
        return {"message": f"Created workflow {name}", "name": name, "workflow": workflow}

    def handle_validate_workflow(self, workflow: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        workflow = workflow or []
        issues = []
        if not workflow:
            issues.append("workflow_is_empty")
        if workflow and workflow[0].get("name", "").lower() == workflow[-1].get("name", "").lower():
            issues.append("first_and_last_steps_should_differ")
        return {"message": "Validated workflow", "valid": not issues, "issues": issues}

    def handle_workflow_to_pipeline(self, workflow: list[dict[str, Any]] | None = None, agent: str = "swarm_agent", **kw: Any) -> dict[str, Any]:
        workflow = workflow or []
        steps = []
        for item in workflow:
            steps.append({"agent": agent, "action": "pipeline", "params": {"stage": item.get("name", "")}})
        return {"message": "Converted workflow to pipeline outline", "pipeline_steps": steps}

    def handle_estimate_workflow(self, workflow: list[dict[str, Any]] | None = None, minutes_per_step: int = 15, **kw: Any) -> dict[str, Any]:
        workflow = workflow or []
        total = len(workflow) * minutes_per_step
        return {"message": "Estimated workflow duration", "steps": len(workflow), "minutes": total, "hours": round(total / 60, 2)}

    def handle_visualize_workflow(self, workflow: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        workflow = workflow or []
        lines = ["flowchart TD"]
        for idx, item in enumerate(workflow):
            lines.append(f"  S{idx}[{item.get('name', f'Step {idx + 1}')}]" )
            if idx > 0:
                lines.append(f"  S{idx - 1} --> S{idx}")
        return {"message": "Visualized workflow", "mermaid": "\n".join(lines)}
