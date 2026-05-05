

from __future__ import annotations

from typing import Any

from agents import BaseAgent

class GovernmentAgent(BaseAgent):

    agent_name = "government_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "government", "status": "ready", "capabilities": ["service_request", "policy_brief", "grant_checklist", "constituent_summary"]}

    def handle_service_request(self, department: str = "", issue: str = "", **kw: Any) -> dict[str, Any]:
        return {"message": "Prepared government service request", "department": department, "issue": issue, "status": "intake_ready"}

    def handle_policy_brief(self, topic: str = "", audience: str = "", **kw: Any) -> dict[str, Any]:
        if not topic:
            raise ValueError("'topic' is required")
        return {"message": "Created policy brief", "topic": topic, "audience": audience or "leadership", "sections": ["context", "options", "risks", "recommendation"]}

    def handle_grant_checklist(self, grant_type: str = "", **kw: Any) -> dict[str, Any]:
        return {"message": "Generated grant checklist", "grant_type": grant_type, "checklist": ["eligibility", "narrative", "budget", "deadlines", "reporting"]}

    def handle_constituent_summary(self, requests: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        requests = requests or []
        return {"message": "Summarized constituent requests", "count": len(requests), "summary": " ".join(requests)[:500]}
