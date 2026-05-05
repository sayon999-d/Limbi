
from __future__ import annotations

from typing import Any

from agents import BaseAgent

class ApprovalAgent(BaseAgent):

    agent_name = "approval_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "approval",
            "status": "ready",
            "capabilities": [
                "create_request",
                "evaluate_approval_need",
                "record_decision",
                "summarize_queue",
                "build_policy",
            ],
        }

    def handle_create_request(self, title: str = "", risk_level: str = "medium", approvers: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        if not title:
            raise ValueError("'title' is required")
        return {
            "message": f"Created approval request for {title}",
            "request": {
                "title": title,
                "risk_level": risk_level,
                "approvers": approvers or ["team_lead"],
                "status": "pending",
            },
        }

    def handle_evaluate_approval_need(self, action: str = "", touches_prod: bool = False, touches_pii: bool = False, **kw: Any) -> dict[str, Any]:
        if not action:
            raise ValueError("'action' is required")
        needs = touches_prod or touches_pii or "delete" in action.lower() or "deploy" in action.lower()
        reasons = []
        if touches_prod:
            reasons.append("production_change")
        if touches_pii:
            reasons.append("sensitive_data")
        if "delete" in action.lower():
            reasons.append("destructive_action")
        return {"message": "Evaluated approval need", "requires_approval": needs, "reasons": reasons}

    def handle_record_decision(self, request_id: str = "", decision: str = "", reviewer: str = "", **kw: Any) -> dict[str, Any]:
        if not request_id or not decision:
            raise ValueError("'request_id' and 'decision' are required")
        return {
            "message": f"Recorded {decision} for {request_id}",
            "record": {"request_id": request_id, "decision": decision, "reviewer": reviewer or "unknown"},
        }

    def handle_summarize_queue(self, requests: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        requests = requests or []
        pending = [item for item in requests if item.get("status") == "pending"]
        approved = [item for item in requests if item.get("status") == "approved"]
        return {
            "message": "Summarized approval queue",
            "total": len(requests),
            "pending": len(pending),
            "approved": len(approved),
        }

    def handle_build_policy(self, name: str = "", rules: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        if not name:
            raise ValueError("'name' is required")
        return {"message": f"Built approval policy {name}", "policy": {"name": name, "rules": rules or ["prod changes require one reviewer"]}}
