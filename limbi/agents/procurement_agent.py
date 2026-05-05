

from __future__ import annotations

from typing import Any

from . import BaseAgent

class ProcurementAgent(BaseAgent):

    agent_name = "procurement_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "procurement", "status": "ready", "capabilities": ["vendor_scorecard", "rfq_outline", "purchase_risk_review", "savings_analysis"]}

    def handle_vendor_scorecard(self, vendor: str = "", cost_score: int = 0, quality_score: int = 0, risk_score: int = 0, **kw: Any) -> dict[str, Any]:
        if not vendor:
            raise ValueError("'vendor' is required")
        total = round((cost_score + quality_score + max(0, 100 - risk_score)) / 3, 2)
        return {"message": f"Scored vendor {vendor}", "score": total}

    def handle_rfq_outline(self, category: str = "", requirements: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        if not category:
            raise ValueError("'category' is required")
        return {"message": "Created RFQ outline", "category": category, "sections": ["scope", "requirements", "timeline", "pricing"], "requirements": requirements or []}

    def handle_purchase_risk_review(self, item: str = "", amount: float = 0.0, **kw: Any) -> dict[str, Any]:
        if not item:
            raise ValueError("'item' is required")
        risk = "high" if amount >= 50000 else "medium" if amount >= 10000 else "low"
        return {"message": "Reviewed purchase risk", "item": item, "risk": risk}

    def handle_savings_analysis(self, current_cost: float = 0.0, proposed_cost: float = 0.0, **kw: Any) -> dict[str, Any]:
        savings = round(current_cost - proposed_cost, 2)
        return {"message": "Calculated savings", "savings": savings, "savings_percent": round((savings / current_cost) * 100, 2) if current_cost else 0}
