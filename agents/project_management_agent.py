from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.project_management")

_projects: dict[str, dict[str, Any]] = {}
_sprints: list[dict[str, Any]] = []


class ProjectManagementAgent(BaseAgent):

    agent_name = "project_management_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "project_management", "status": "ready", "projects": len(_projects), "capabilities": ["create_project", "create_sprint", "velocity_report", "burndown", "risk_register"]}

    def handle_create_project(self, name: str = "", description: str = "", methodology: str = "scrum", team_size: int = 5, **kw: Any) -> dict[str, Any]:
        if not name:
            raise ValueError("A project 'name' is required")
        pid = f"PRJ-{str(uuid.uuid4())[:6].upper()}"
        project = {"id": pid, "name": name, "description": description, "methodology": methodology, "team_size": team_size, "status": "planning", "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "epics": [], "sprints": []}
        _projects[pid] = project
        return {"message": f"Project '{name}' created ({pid})", "project": project}

    def handle_create_sprint(self, project_id: str = "", name: str = "", duration_weeks: int = 2, goals: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        if not name:
            raise ValueError("Sprint 'name' is required")
        sprint = {"id": f"SPR-{str(uuid.uuid4())[:6].upper()}", "project_id": project_id, "name": name, "duration_weeks": duration_weeks, "goals": goals or [], "status": "planned", "velocity": 0, "stories_completed": 0, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        _sprints.append(sprint)
        return {"message": f"Sprint '{name}' created", "sprint": sprint}

    def handle_velocity_report(self, sprints_data: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        data = sprints_data or [{"sprint": f"Sprint {i+1}", "planned": 20+i*2, "completed": 18+i} for i in range(5)]
        avg_velocity = sum(s.get("completed", 0) for s in data) / max(len(data), 1)
        return {"message": f"Velocity report: avg {avg_velocity:.1f} pts/sprint over {len(data)} sprints", "sprints": data, "average_velocity": round(avg_velocity, 1), "trend": "improving" if len(data) > 1 and data[-1].get("completed", 0) > data[0].get("completed", 0) else "stable"}

    def handle_burndown(self, total_points: int = 50, days_elapsed: int = 5, total_days: int = 10, points_remaining: int = 30, **kw: Any) -> dict[str, Any]:
        ideal_remaining = total_points * (1 - days_elapsed / max(total_days, 1))
        pace = "on_track" if abs(points_remaining - ideal_remaining) < total_points * 0.1 else "behind" if points_remaining > ideal_remaining else "ahead"
        return {"message": f"Burndown: {points_remaining}/{total_points} pts remaining — {pace}", "total_points": total_points, "points_remaining": points_remaining, "ideal_remaining": round(ideal_remaining, 1), "days_elapsed": days_elapsed, "total_days": total_days, "pace": pace, "projected_completion": "on time" if pace != "behind" else f"~{int((points_remaining / max(total_points - points_remaining, 1)) * days_elapsed)} days late"}

    def handle_risk_register(self, risks: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        risks = risks or [{"title": "Scope creep", "probability": "high", "impact": "high"}, {"title": "Key person dependency", "probability": "medium", "impact": "high"}, {"title": "Third-party API instability", "probability": "low", "impact": "medium"}]
        scored = []
        score_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        for r in risks:
            p = score_map.get(r.get("probability", "medium"), 2)
            i = score_map.get(r.get("impact", "medium"), 2)
            scored.append({**r, "risk_score": p * i, "priority": "critical" if p*i >= 9 else "high" if p*i >= 6 else "medium" if p*i >= 3 else "low"})
        scored.sort(key=lambda x: x["risk_score"], reverse=True)
        return {"message": f"Risk register: {len(scored)} risks tracked", "risks": scored}
