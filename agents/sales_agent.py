

from __future__ import annotations

from typing import Any

from agents import BaseAgent

class SalesAgent(BaseAgent):

    agent_name = "sales_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "sales",
            "status": "ready",
            "capabilities": [
                "qualify_lead",
                "draft_outreach",
                "generate_discovery_questions",
                "proposal_outline",
                "forecast_deal",
            ],
        }

    def handle_qualify_lead(self, company: str = "", budget: int = 0, urgency: str = "medium", **kw: Any) -> dict[str, Any]:
        if not company:
            raise ValueError("'company' is required")
        score = 40
        score += 20 if budget >= 10000 else 0
        score += 20 if urgency.lower() == "high" else 10
        qualification = "hot" if score >= 70 else "warm" if score >= 50 else "cold"
        return {"message": f"Qualified lead {company}", "score": score, "qualification": qualification}

    def handle_draft_outreach(self, prospect_name: str = "", company: str = "", pain_point: str = "", **kw: Any) -> dict[str, Any]:
        if not company:
            raise ValueError("'company' is required")
        text = (
            f"Hi {prospect_name or 'there'},\n\n"
            f"I noticed {company} may be dealing with {pain_point or 'workflow complexity'}. "
            "We help teams streamline operations with agent-driven automation. "
            "Would a short intro call next week be useful?\n"
        )
        return {"message": "Drafted outreach", "outreach": text}

    def handle_generate_discovery_questions(self, use_case: str = "", **kw: Any) -> dict[str, Any]:
        if not use_case:
            raise ValueError("'use_case' is required")
        questions = [
            "What process is most painful today?",
            "How are you measuring success?",
            "Which teams would use this first?",
            "What security or compliance requirements matter?",
        ]
        return {"message": f"Generated discovery questions for {use_case}", "questions": questions}

    def handle_proposal_outline(self, client: str = "", solution: str = "", **kw: Any) -> dict[str, Any]:
        if not client or not solution:
            raise ValueError("'client' and 'solution' are required")
        outline = ["executive summary", "problem statement", "proposed solution", "implementation plan", "pricing", "next steps"]
        return {"message": f"Created proposal outline for {client}", "outline": outline, "solution": solution}

    def handle_forecast_deal(self, stage: str = "", amount: float = 0.0, **kw: Any) -> dict[str, Any]:
        if not stage:
            raise ValueError("'stage' is required")
        probabilities = {"discovery": 0.2, "proposal": 0.5, "negotiation": 0.7, "verbal_commit": 0.9}
        probability = probabilities.get(stage.lower(), 0.3)
        return {"message": "Forecasted deal", "weighted_value": round(amount * probability, 2), "probability": probability}
