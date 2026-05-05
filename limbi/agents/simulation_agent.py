

from __future__ import annotations

from typing import Any

from . import BaseAgent

class SimulationAgent(BaseAgent):

    agent_name = "simulation_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "simulation",
            "status": "ready",
            "capabilities": [
                "run_scenario",
                "compare_strategies",
                "build_risk_matrix",
                "estimate_outcomes",
                "sensitivity_analysis",
            ],
        }

    def handle_run_scenario(self, name: str = "", assumptions: dict[str, float] | None = None, **kw: Any) -> dict[str, Any]:
        if not name:
            raise ValueError("'name' is required")
        assumptions = assumptions or {"revenue": 100.0, "cost": 60.0, "risk": 0.2}
        score = assumptions.get("revenue", 0) - assumptions.get("cost", 0) - (assumptions.get("risk", 0) * 100)
        return {"message": f"Ran scenario {name}", "score": round(score, 2), "assumptions": assumptions}

    def handle_compare_strategies(self, strategies: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        strategies = strategies or []
        ranked = sorted(strategies, key=lambda item: item.get("expected_value", 0) - item.get("risk_penalty", 0), reverse=True)
        return {"message": "Compared strategies", "ranked": ranked}

    def handle_build_risk_matrix(self, risks: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        risks = risks or []
        matrix = []
        for risk in risks:
            impact = risk.get("impact", 0)
            likelihood = risk.get("likelihood", 0)
            matrix.append({**risk, "score": impact * likelihood})
        return {"message": "Built risk matrix", "matrix": sorted(matrix, key=lambda item: item["score"], reverse=True)}

    def handle_estimate_outcomes(self, best_case: float = 0.0, base_case: float = 0.0, worst_case: float = 0.0, **kw: Any) -> dict[str, Any]:
        expected = round((best_case * 0.2) + (base_case * 0.6) + (worst_case * 0.2), 2)
        return {"message": "Estimated weighted outcome", "expected": expected}

    def handle_sensitivity_analysis(self, variable: str = "", values: list[float] | None = None, formula_base: float = 100.0, **kw: Any) -> dict[str, Any]:
        if not variable:
            raise ValueError("'variable' is required")
        values = values or [0.8, 1.0, 1.2]
        outcomes = [{"value": value, "outcome": round(formula_base * value, 2)} for value in values]
        return {"message": f"Completed sensitivity analysis for {variable}", "outcomes": outcomes}
