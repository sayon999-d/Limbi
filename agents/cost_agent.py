from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.cost")


class CostAgent(BaseAgent):

    agent_name = "cost_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "cost_management", "status": "ready", "capabilities": ["cloud_cost_report", "budget_alert", "cost_forecast", "resource_rightsizing", "savings_plan"]}

    def handle_cloud_cost_report(self, provider: str = "aws", period: str = "monthly", **kw: Any) -> dict[str, Any]:
        services = [
            {"service": "Compute", "cost": 2450.00, "change": "+5%"},
            {"service": "Storage", "cost": 890.50, "change": "-2%"},
            {"service": "Database", "cost": 1200.00, "change": "+12%"},
            {"service": "Networking", "cost": 340.00, "change": "+1%"},
            {"service": "AI/ML", "cost": 780.00, "change": "+25%"},
        ]
        total = sum(s["cost"] for s in services)
        return {"message": f"Cloud cost report ({provider}, {period}): ${total:,.2f}", "provider": provider, "period": period, "services": services, "total": total, "currency": "USD"}

    def handle_budget_alert(self, budget: float = 0, current_spend: float = 0, period: str = "monthly", **kw: Any) -> dict[str, Any]:
        if not budget:
            raise ValueError("'budget' amount is required")
        utilization = current_spend / max(budget, 0.01) * 100
        status = "critical" if utilization > 100 else "warning" if utilization > 80 else "on_track"
        return {"message": f"Budget: ${current_spend:,.2f} / ${budget:,.2f} ({utilization:.1f}%) — {status}", "budget": budget, "current_spend": current_spend, "utilization_pct": round(utilization, 1), "status": status, "remaining": round(budget - current_spend, 2)}

    def handle_cost_forecast(self, current_monthly: float = 0, growth_rate: float = 5.0, months: int = 6, **kw: Any) -> dict[str, Any]:
        forecast = []
        cost = current_monthly
        for i in range(months):
            cost *= (1 + growth_rate / 100)
            forecast.append({"month": i + 1, "projected_cost": round(cost, 2)})
        total_projected = sum(f["projected_cost"] for f in forecast)
        return {"message": f"{months}-month forecast at {growth_rate}% growth: ${total_projected:,.2f} total", "current_monthly": current_monthly, "growth_rate_pct": growth_rate, "forecast": forecast, "total_projected": round(total_projected, 2)}

    def handle_resource_rightsizing(self, resources: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        resources = resources or [
            {"name": "web-server-1", "current_type": "m5.xlarge", "avg_cpu": 15, "avg_memory": 20},
            {"name": "db-primary", "current_type": "r5.2xlarge", "avg_cpu": 60, "avg_memory": 45},
        ]
        recommendations = []
        for r in resources:
            cpu = r.get("avg_cpu", 50)
            if cpu < 25:
                recommendations.append({**r, "recommendation": "Downsize", "potential_savings": "40-60%"})
            elif cpu > 80:
                recommendations.append({**r, "recommendation": "Upsize", "potential_savings": "N/A (perf improvement)"})
            else:
                recommendations.append({**r, "recommendation": "Right-sized", "potential_savings": "0%"})
        return {"message": f"Rightsizing analysis for {len(resources)} resources", "recommendations": recommendations}

    def handle_savings_plan(self, monthly_spend: float = 0, commitment_term: str = "1_year", **kw: Any) -> dict[str, Any]:
        discounts = {"1_year": 0.30, "3_year": 0.50, "spot": 0.70}
        discount = discounts.get(commitment_term, 0.30)
        savings = monthly_spend * discount
        return {"message": f"Savings plan ({commitment_term}): save ${savings:,.2f}/mo ({discount*100:.0f}% discount)", "monthly_spend": monthly_spend, "commitment_term": commitment_term, "discount_pct": discount * 100, "monthly_savings": round(savings, 2), "annual_savings": round(savings * 12, 2)}
