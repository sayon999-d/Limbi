

from __future__ import annotations

from typing import Any

from agents import BaseAgent

class HRAgent(BaseAgent):

    agent_name = "hr_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "hr", "status": "ready", "capabilities": ["onboarding_plan", "policy_summary", "performance_review_outline", "leave_guidance"]}

    def handle_onboarding_plan(self, role: str = "", start_date: str = "", **kw: Any) -> dict[str, Any]:
        if not role:
            raise ValueError("'role' is required")
        return {"message": f"Created onboarding plan for {role}", "start_date": start_date, "steps": ["equipment", "access", "orientation", "30-day check-in"]}

    def handle_policy_summary(self, policy_text: str = "", **kw: Any) -> dict[str, Any]:
        if not policy_text:
            raise ValueError("'policy_text' is required")
        return {"message": "Summarized HR policy", "summary": policy_text[:400]}

    def handle_performance_review_outline(self, employee_level: str = "", **kw: Any) -> dict[str, Any]:
        return {"message": "Generated review outline", "sections": ["wins", "growth areas", "goals", "manager support"], "employee_level": employee_level or "general"}

    def handle_leave_guidance(self, leave_type: str = "", days_requested: int = 0, **kw: Any) -> dict[str, Any]:
        return {"message": "Prepared leave guidance", "leave_type": leave_type or "general", "days_requested": days_requested, "checks": ["policy eligibility", "manager approval", "coverage plan"]}
