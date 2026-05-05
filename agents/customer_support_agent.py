

from __future__ import annotations

from typing import Any

from agents import BaseAgent

class CustomerSupportAgent(BaseAgent):

    agent_name = "customer_support_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "customer_support",
            "status": "ready",
            "capabilities": [
                "classify_ticket",
                "draft_reply",
                "suggest_next_best_action",
                "summarize_case",
                "generate_escalation",
            ],
        }

    def handle_classify_ticket(self, message: str = "", **kw: Any) -> dict[str, Any]:
        if not message:
            raise ValueError("'message' is required")
        text = message.lower()
        category = "general"
        priority = "medium"
        if "refund" in text or "billing" in text:
            category = "billing"
        elif "bug" in text or "broken" in text or "error" in text:
            category = "technical"
            priority = "high"
        elif "feature" in text:
            category = "feature_request"
        return {"message": "Classified support ticket", "category": category, "priority": priority}

    def handle_draft_reply(self, customer_name: str = "", issue: str = "", tone: str = "empathetic", **kw: Any) -> dict[str, Any]:
        if not issue:
            raise ValueError("'issue' is required")
        greeting = f"Hi {customer_name}," if customer_name else "Hello,"
        body = f"{greeting}\n\nThanks for reaching out. We understand the issue: {issue}.\nWe are reviewing it and will follow up with the next update.\n\nBest,\nSupport"
        return {"message": "Drafted support reply", "reply": body, "tone": tone}

    def handle_suggest_next_best_action(self, category: str = "", priority: str = "medium", **kw: Any) -> dict[str, Any]:
        if not category:
            raise ValueError("'category' is required")
        action = "respond_with_acknowledgement"
        if category == "technical" and priority == "high":
            action = "escalate_to_engineering"
        elif category == "billing":
            action = "route_to_finance_or_billing_queue"
        return {"message": "Suggested next best action", "action": action}

    def handle_summarize_case(self, messages: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        messages = messages or []
        summary = " ".join(messages)[:500]
        return {"message": "Summarized support case", "message_count": len(messages), "summary": summary}

    def handle_generate_escalation(self, issue: str = "", owner_team: str = "engineering", **kw: Any) -> dict[str, Any]:
        if not issue:
            raise ValueError("'issue' is required")
        return {"message": "Generated escalation note", "escalation": {"owner_team": owner_team, "issue": issue, "severity": "high"}}
