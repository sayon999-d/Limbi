

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.planner")

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"

@dataclass
class PlanTask:

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    description: str = ""
    agent: str = ""
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 5
    estimated_cost: float = 0.0
    estimated_time_min: float = 0.0
    risk_score: float = 0.0
    impact_score: float = 0.5
    result: dict[str, Any] | None = None

    def utility_score(self, weights: dict[str, float] | None = None) -> float:

        w = weights or {"impact": 0.4, "time": 0.2, "cost": 0.2, "risk": 0.2}
        time_norm = max(0, 1 - self.estimated_time_min / 60)
        cost_norm = max(0, 1 - self.estimated_cost / 100)
        risk_norm = 1 - self.risk_score
        return (
            w.get("impact", 0.25) * self.impact_score +
            w.get("time", 0.25) * time_norm +
            w.get("cost", 0.25) * cost_norm +
            w.get("risk", 0.25) * risk_norm
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "agent": self.agent,
            "action": self.action,
            "params": self.params,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "priority": self.priority,
            "estimated_cost": self.estimated_cost,
            "estimated_time_min": self.estimated_time_min,
            "risk_score": self.risk_score,
            "impact_score": self.impact_score,
            "utility_score": round(self.utility_score(), 3),
        }

@dataclass
class Plan:

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal: str = ""
    tasks: list[PlanTask] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    status: str = "draft"
    total_utility: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status,
            "total_utility": round(self.total_utility, 3),
            "task_count": len(self.tasks),
            "tasks": [t.to_dict() for t in self.tasks],
            "execution_order": self._execution_order(),
        }

    def _execution_order(self) -> list[list[str]]:

        completed: set[str] = set()
        remaining = {t.id: set(t.dependencies) for t in self.tasks}
        layers: list[list[str]] = []

        while remaining:
            ready = [tid for tid, deps in remaining.items() if deps <= completed]
            if not ready:
                break
            layers.append(ready)
            for tid in ready:
                completed.add(tid)
                del remaining[tid]
            for deps in remaining.values():
                deps -= completed

        return layers

_plans: dict[str, Plan] = {}

class GoalPlannerAgent(BaseAgent):

    agent_name = "planner_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "goal_utility_planner",
            "status": "ready",
            "active_plans": len(_plans),
        }

    def handle_create_plan(
        self,
        goal: str = "",
        tasks: list[dict[str, Any]] | None = None,
        prompt: str = "",
        task: str = "",
        description: str = "",
        objective: str = "",
        query: str = "",
        **kw: Any,
    ) -> dict[str, Any]:

        goal = goal or prompt or task or description or objective or query
        if not goal:
            raise ValueError("A 'goal' is required to create a plan")

        plan = Plan(goal=goal)
        task_name_to_id: dict[str, str] = {}

        for t in (tasks or []):
            task = PlanTask(
                title=t.get("title", "Untitled"),
                description=t.get("description", ""),
                agent=t.get("agent", ""),
                action=t.get("action", ""),
                params=t.get("params", {}),
                priority=t.get("priority", 5),
                estimated_cost=t.get("estimated_cost", 0.0),
                estimated_time_min=t.get("estimated_time_min", 5.0),
                risk_score=t.get("risk_score", 0.2),
                impact_score=t.get("impact_score", 0.5),
            )
            task_name_to_id[task.title] = task.id
            plan.tasks.append(task)

        for t_dict, task in zip(tasks or [], plan.tasks):
            for dep_name in t_dict.get("dependencies", []):
                dep_id = task_name_to_id.get(dep_name, dep_name)
                task.dependencies.append(dep_id)

        plan.total_utility = sum(t.utility_score() for t in plan.tasks) / max(len(plan.tasks), 1)
        plan.status = "ready"

        _plans[plan.id] = plan
        logger.info("Created plan '%s' with %d tasks (utility=%.3f)", plan.id, len(plan.tasks), plan.total_utility)

        return {
            "message": f"Plan created for goal: '{goal}'",
            **plan.to_dict(),
        }

    def handle_optimize_plan(
        self,
        plan_id: str = "",
        weights: dict[str, float] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        plan = _plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan '{plan_id}' not found")

        w = weights or {"impact": 0.4, "time": 0.2, "cost": 0.2, "risk": 0.2}

        for task in plan.tasks:
            task.priority = int(task.utility_score(w) * 10)

        plan.total_utility = sum(t.utility_score(w) for t in plan.tasks) / max(len(plan.tasks), 1)

        return {
            "message": f"Plan '{plan_id}' optimized with weights {w}",
            **plan.to_dict(),
        }

    def handle_get_plan(self, plan_id: str = "", **kw: Any) -> dict[str, Any]:

        plan = _plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan '{plan_id}' not found")
        return plan.to_dict()

    def handle_list_plans(self, **kw: Any) -> dict[str, Any]:

        return {
            "plans": [
                {"id": p.id, "goal": p.goal, "tasks": len(p.tasks), "status": p.status, "utility": round(p.total_utility, 3)}
                for p in _plans.values()
            ],
            "total": len(_plans),
        }

    def handle_decompose_goal(
        self,
        goal: str = "",
        context: str = "",
        prompt: str = "",
        task: str = "",
        description: str = "",
        objective: str = "",
        query: str = "",
        **kw: Any,
    ) -> dict[str, Any]:

        goal = goal or prompt or task or description or objective or query
        templates: dict[str, list[dict[str, Any]]] = {
            "deploy": [
                {"title": "Run tests", "agent": "devops_agent", "action": "run_pipeline", "impact_score": 0.8, "risk_score": 0.1},
                {"title": "Create feature branch", "agent": "git_agent", "action": "create_branch", "dependencies": ["Run tests"], "impact_score": 0.6},
                {"title": "Create PR", "agent": "git_agent", "action": "create_pr", "dependencies": ["Create feature branch"], "impact_score": 0.7},
                {"title": "Deploy to staging", "agent": "devops_agent", "action": "deploy_branch", "dependencies": ["Create PR"], "risk_score": 0.3, "impact_score": 0.9},
                {"title": "Create tracking ticket", "agent": "jira_agent", "action": "create_ticket", "impact_score": 0.4, "risk_score": 0.0},
            ],
            "fix": [
                {"title": "Investigate issue", "agent": "devops_agent", "action": "check_status", "impact_score": 0.7},
                {"title": "Create fix branch", "agent": "git_agent", "action": "create_branch", "dependencies": ["Investigate issue"], "impact_score": 0.6},
                {"title": "Create bug ticket", "agent": "jira_agent", "action": "create_ticket", "impact_score": 0.5},
                {"title": "Deploy fix", "agent": "devops_agent", "action": "deploy_branch", "dependencies": ["Create fix branch"], "risk_score": 0.4, "impact_score": 0.9},
            ],
            "infrastructure": [
                {"title": "Check EC2 instances", "agent": "aws_agent", "action": "describe_instances", "impact_score": 0.5},
                {"title": "Review S3 buckets", "agent": "aws_agent", "action": "list_s3_buckets", "impact_score": 0.4},
                {"title": "Check CloudWatch", "agent": "aws_agent", "action": "get_cloudwatch_metrics", "impact_score": 0.6},
                {"title": "Create audit ticket", "agent": "jira_agent", "action": "create_ticket", "dependencies": ["Check EC2 instances", "Review S3 buckets", "Check CloudWatch"], "impact_score": 0.7},
            ],
        }

        goal_lower = goal.lower()
        matched_template = None
        for keyword, template in templates.items():
            if keyword in goal_lower:
                matched_template = template
                break

        if matched_template:
            return {
                "message": f"Decomposed goal into {len(matched_template)} tasks",
                "goal": goal,
                "suggested_tasks": matched_template,
                "note": "Use 'create_plan' with these tasks, or modify them first",
            }

        return {
            "message": "Could not auto-decompose - use the LLM orchestrator for complex goals",
            "goal": goal,
            "suggested_tasks": [
                {"title": f"Analyze: {goal}", "agent": "", "action": "", "impact_score": 0.5},
                {"title": f"Execute: {goal}", "agent": "", "action": "", "dependencies": [f"Analyze: {goal}"], "impact_score": 0.8},
                {"title": f"Verify: {goal}", "agent": "", "action": "", "dependencies": [f"Execute: {goal}"], "impact_score": 0.6},
            ],
        }
