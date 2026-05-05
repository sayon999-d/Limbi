

from __future__ import annotations

from typing import Any

from . import BaseAgent

class FinanceAgent(BaseAgent):

    agent_name = "finance_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "finance",
            "status": "ready",
            "capabilities": [
                "analyze_budget_variance",
                "expense_policy_check",
                "invoice_summary",
                "unit_economics",
                "forecast_cashflow",
            ],
        }

    def handle_analyze_budget_variance(self, planned: float = 0.0, actual: float = 0.0, **kw: Any) -> dict[str, Any]:
        variance = actual - planned
        pct = round((variance / planned) * 100, 2) if planned else 0
        return {"message": "Analyzed budget variance", "variance": round(variance, 2), "variance_percent": pct}

    def handle_expense_policy_check(self, category: str = "", amount: float = 0.0, **kw: Any) -> dict[str, Any]:
        if not category:
            raise ValueError("'category' is required")
        limit = 100 if category.lower() == "meals" else 1000
        return {"message": "Checked expense policy", "approved": amount <= limit, "limit": limit, "amount": amount}

    def handle_invoice_summary(self, line_items: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        line_items = line_items or []
        total = round(sum(float(item.get("amount", 0)) for item in line_items), 2)
        return {"message": "Summarized invoice", "line_item_count": len(line_items), "total": total}

    def handle_unit_economics(self, revenue: float = 0.0, variable_cost: float = 0.0, customers: int = 1, **kw: Any) -> dict[str, Any]:
        contribution = revenue - variable_cost
        arpu = round(revenue / customers, 2) if customers else 0
        return {"message": "Calculated unit economics", "contribution_margin": round(contribution, 2), "arpu": arpu}

    def handle_forecast_cashflow(self, starting_cash: float = 0.0, monthly_in: float = 0.0, monthly_out: float = 0.0, months: int = 6, **kw: Any) -> dict[str, Any]:
        balance = starting_cash
        projection = []
        for month in range(1, months + 1):
            balance += monthly_in - monthly_out
            projection.append({"month": month, "ending_cash": round(balance, 2)})
        return {"message": "Forecasted cashflow", "projection": projection}
