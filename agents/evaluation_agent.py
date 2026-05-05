

from __future__ import annotations

from typing import Any

from agents import BaseAgent

class EvaluationAgent(BaseAgent):

    agent_name = "evaluation_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "evaluation",
            "status": "ready",
            "capabilities": [
                "score_output",
                "compare_candidates",
                "generate_rubric",
                "benchmark_agents",
                "regression_guard",
            ],
        }

    def handle_score_output(self, output: str = "", rubric: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        if not output:
            raise ValueError("'output' is required")
        rubric = rubric or ["correctness", "clarity", "completeness"]
        score = min(10, max(1, len(output.split()) // 20 + 3))
        return {"message": "Scored output", "score": score, "rubric": rubric}

    def handle_compare_candidates(self, candidates: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        candidates = candidates or []
        ranked = sorted(candidates, key=lambda item: item.get("score", 0), reverse=True)
        winner = ranked[0] if ranked else None
        return {"message": "Compared candidates", "winner": winner, "ranking": ranked}

    def handle_generate_rubric(self, goal: str = "", **kw: Any) -> dict[str, Any]:
        if not goal:
            raise ValueError("'goal' is required")
        rubric = [
            {"criterion": "task_success", "weight": 0.4},
            {"criterion": "quality", "weight": 0.25},
            {"criterion": "safety", "weight": 0.2},
            {"criterion": "efficiency", "weight": 0.15},
        ]
        return {"message": f"Generated rubric for {goal}", "rubric": rubric}

    def handle_benchmark_agents(self, runs: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        runs = runs or []
        summary = {}
        for run in runs:
            name = run.get("agent", "unknown")
            score = float(run.get("score", 0))
            summary.setdefault(name, []).append(score)
        bench = [{"agent": name, "avg_score": round(sum(scores) / len(scores), 3), "runs": len(scores)} for name, scores in summary.items()]
        bench.sort(key=lambda item: item["avg_score"], reverse=True)
        return {"message": "Benchmarked agents", "benchmark": bench}

    def handle_regression_guard(self, current_score: float = 0.0, baseline_score: float = 0.0, tolerance: float = 0.05, **kw: Any) -> dict[str, Any]:
        delta = current_score - baseline_score
        passed = delta >= -abs(tolerance)
        return {"message": "Checked regression guard", "passed": passed, "delta": round(delta, 4), "tolerance": tolerance}
