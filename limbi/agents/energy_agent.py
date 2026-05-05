from __future__ import annotations

import logging
from typing import Any

from . import BaseAgent

logger = logging.getLogger("limbi.agents.energy")


class EnergyAgent(BaseAgent):

    agent_name = "energy_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "energy", "status": "ready", "capabilities": ["consumption_report", "carbon_footprint", "optimize_usage", "renewable_mix", "cost_analysis"]}

    def handle_consumption_report(self, facility: str = "", period: str = "monthly", kwh: float = 0, **kw: Any) -> dict[str, Any]:
        return {"message": f"Energy consumption for {facility or 'facility'}: {kwh} kWh ({period})", "facility": facility, "period": period, "kwh": kwh, "cost_estimate": round(kwh * 0.12, 2), "comparison": "8% below average" if kwh < 50000 else "12% above average"}

    def handle_carbon_footprint(self, kwh: float = 0, source_mix: dict[str, float] | None = None, **kw: Any) -> dict[str, Any]:
        mix = source_mix or {"grid": 0.7, "solar": 0.2, "wind": 0.1}
        emission_factors = {"grid": 0.42, "solar": 0.05, "wind": 0.01, "nuclear": 0.02, "coal": 0.95, "gas": 0.55}
        total_kg = sum(kwh * pct * emission_factors.get(src, 0.42) for src, pct in mix.items())
        return {"message": f"Carbon footprint: {total_kg:.1f} kg CO₂", "kwh": kwh, "co2_kg": round(total_kg, 1), "source_mix": mix, "trees_equivalent": round(total_kg / 21, 1)}

    def handle_optimize_usage(self, current_kwh: float = 0, recommendations: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        recs = recommendations or ["Shift workloads to off-peak hours", "Enable auto-scaling down during low traffic", "Use spot/preemptible instances", "Consolidate underutilized servers"]
        savings_pct = 15
        return {"message": f"Optimization potential: ~{savings_pct}% savings", "current_kwh": current_kwh, "projected_savings_kwh": round(current_kwh * savings_pct / 100, 1), "recommendations": recs}

    def handle_renewable_mix(self, target_pct: float = 100, current_pct: float = 30, **kw: Any) -> dict[str, Any]:
        gap = target_pct - current_pct
        return {"message": f"Renewable energy: {current_pct}% → target {target_pct}%", "current_pct": current_pct, "target_pct": target_pct, "gap_pct": gap, "strategy": "Purchase RECs or sign PPA" if gap > 30 else "On track"}

    def handle_cost_analysis(self, kwh: float = 0, rate_per_kwh: float = 0.12, peak_pct: float = 40, **kw: Any) -> dict[str, Any]:
        peak_cost = kwh * peak_pct / 100 * rate_per_kwh * 1.5
        offpeak_cost = kwh * (100 - peak_pct) / 100 * rate_per_kwh
        total = peak_cost + offpeak_cost
        return {"message": f"Energy cost analysis: ${total:,.2f}", "total_cost": round(total, 2), "peak_cost": round(peak_cost, 2), "offpeak_cost": round(offpeak_cost, 2), "savings_if_shift_10pct_offpeak": round(total * 0.05, 2)}
