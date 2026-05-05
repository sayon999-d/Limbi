

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.reflex")

@dataclass
class Rule:

    name: str
    condition: str
    action_type: str
    action_params: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    cooldown_seconds: float = 60.0
    last_fired: float = 0.0

_DEFAULT_RULES: list[Rule] = [
    Rule(
        name="cpu_critical",
        condition="state.get('cpu_percent', 0) > 90",
        action_type="alert",
        action_params={"severity": "critical", "message": "CPU above 90%!"},
        priority=10,
        cooldown_seconds=120,
    ),
    Rule(
        name="memory_warning",
        condition="state.get('memory_percent', 0) > 80",
        action_type="alert",
        action_params={"severity": "warning", "message": "Memory above 80%"},
        priority=5,
        cooldown_seconds=300,
    ),
    Rule(
        name="disk_full",
        condition="state.get('disk_percent', 0) > 95",
        action_type="alert",
        action_params={"severity": "critical", "message": "Disk nearly full (>95%)"},
        priority=10,
        cooldown_seconds=600,
    ),
    Rule(
        name="auto_scale_up",
        condition="state.get('request_rate', 0) > 1000 and state.get('cpu_percent', 0) > 75",
        action_type="scale",
        action_params={"direction": "up", "increment": 1},
        priority=8,
        cooldown_seconds=180,
    ),
    Rule(
        name="auto_scale_down",
        condition="state.get('request_rate', 0) < 100 and state.get('instance_count', 1) > 1",
        action_type="scale",
        action_params={"direction": "down", "increment": 1},
        priority=3,
        cooldown_seconds=300,
    ),
    Rule(
        name="error_spike",
        condition="state.get('error_rate', 0) > 5",
        action_type="alert",
        action_params={"severity": "warning", "message": "Error rate spike detected (>5%)"},
        priority=9,
        cooldown_seconds=120,
    ),
    Rule(
        name="deployment_health",
        condition="state.get('health_check_failures', 0) >= 3",
        action_type="execute",
        action_params={"action": "rollback", "reason": "3+ consecutive health check failures"},
        priority=10,
        cooldown_seconds=300,
    ),
]

class SimpleReflexAgent(BaseAgent):

    agent_name = "reflex_agent"

    def __init__(self) -> None:
        self._rules = list(_DEFAULT_RULES)

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "simple_reflex",
            "status": "ready",
            "rules_loaded": len(self._rules),
        }

    def handle_evaluate(self, state: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:

        state = state or {}
        now = time.time()
        fired: list[dict[str, Any]] = []

        for rule in sorted(self._rules, key=lambda r: r.priority, reverse=True):
            if now - rule.last_fired < rule.cooldown_seconds:
                continue
            try:
                if eval(rule.condition, {"__builtins__": {}}, {"state": state}):
                    rule.last_fired = now
                    fired.append({
                        "rule": rule.name,
                        "action_type": rule.action_type,
                        "action_params": rule.action_params,
                        "priority": rule.priority,
                    })
            except Exception as exc:
                logger.warning("Rule '%s' eval error: %s", rule.name, exc)

        return {
            "message": f"Evaluated {len(self._rules)} rules, {len(fired)} fired",
            "input_state": state,
            "fired_rules": fired,
            "total_rules": len(self._rules),
        }

    def handle_add_rule(
        self,
        name: str = "",
        condition: str = "",
        action_type: str = "alert",
        action_params: dict[str, Any] | None = None,
        priority: int = 5,
        cooldown_seconds: float = 60.0,
        **kw: Any,
    ) -> dict[str, Any]:

        if not name or not condition:
            raise ValueError("Both 'name' and 'condition' are required")
        rule = Rule(
            name=name,
            condition=condition,
            action_type=action_type,
            action_params=action_params or {},
            priority=priority,
            cooldown_seconds=cooldown_seconds,
        )
        self._rules.append(rule)
        return {"message": f"Rule '{name}' added", "total_rules": len(self._rules)}

    def handle_list_rules(self, **kw: Any) -> dict[str, Any]:

        return {
            "rules": [
                {
                    "name": r.name,
                    "condition": r.condition,
                    "action_type": r.action_type,
                    "priority": r.priority,
                    "cooldown_seconds": r.cooldown_seconds,
                }
                for r in sorted(self._rules, key=lambda r: r.priority, reverse=True)
            ],
            "total": len(self._rules),
        }

class ModelBasedReflexAgent(BaseAgent):

    agent_name = "model_reflex_agent"

    def __init__(self) -> None:
        self._state_history: deque[dict[str, Any]] = deque(maxlen=100)
        self._current_model: dict[str, Any] = {}
        self._anomaly_thresholds: dict[str, float] = {
            "cpu_percent": 2.0,
            "memory_percent": 2.0,
            "error_rate": 1.5,
            "request_rate": 2.5,
        }

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "model_based_reflex",
            "status": "ready",
            "history_size": len(self._state_history),
            "tracked_metrics": list(self._current_model.keys()),
        }

    def handle_update_model(self, state: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:

        state = state or {}
        state["_timestamp"] = time.time()
        self._state_history.append(state)

        anomalies: list[dict[str, Any]] = []
        for key, value in state.items():
            if key.startswith("_") or not isinstance(value, (int, float)):
                continue

            historical = [s.get(key) for s in self._state_history if key in s and isinstance(s.get(key), (int, float))]

            if len(historical) < 3:
                self._current_model[key] = {"mean": value, "std": 0, "trend": "insufficient_data"}
                continue

            mean = sum(historical) / len(historical)
            variance = sum((x - mean) ** 2 for x in historical) / len(historical)
            std = variance ** 0.5

            recent = historical[-5:] if len(historical) >= 5 else historical
            trend = "stable"
            if len(recent) >= 3:
                if all(recent[i] < recent[i + 1] for i in range(len(recent) - 1)):
                    trend = "rising"
                elif all(recent[i] > recent[i + 1] for i in range(len(recent) - 1)):
                    trend = "falling"

            self._current_model[key] = {
                "mean": round(mean, 2),
                "std": round(std, 2),
                "current": value,
                "trend": trend,
                "samples": len(historical),
            }

            threshold = self._anomaly_thresholds.get(key, 2.0)
            if std > 0 and abs(value - mean) > threshold * std:
                anomalies.append({
                    "metric": key,
                    "current": value,
                    "mean": round(mean, 2),
                    "std_devs_away": round(abs(value - mean) / std, 1),
                    "direction": "above" if value > mean else "below",
                })

        return {
            "message": f"Model updated with {len(state) - 1} metrics, {len(anomalies)} anomalies detected",
            "model": self._current_model,
            "anomalies": anomalies,
            "history_size": len(self._state_history),
        }

    def handle_predict_next(self, metric: str = "", **kw: Any) -> dict[str, Any]:

        if metric not in self._current_model:
            return {"message": f"No data for metric '{metric}'", "available": list(self._current_model.keys())}

        historical = [
            s.get(metric) for s in self._state_history
            if metric in s and isinstance(s.get(metric), (int, float))
        ]
        if len(historical) < 2:
            return {"message": "Not enough data for prediction", "metric": metric}

        recent = historical[-10:]
        n = len(recent)
        x_mean = (n - 1) / 2
        y_mean = sum(recent) / n
        slope_num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(recent))
        slope_den = sum((i - x_mean) ** 2 for i in range(n))
        slope = slope_num / slope_den if slope_den != 0 else 0
        predicted = recent[-1] + slope

        return {
            "metric": metric,
            "current": recent[-1],
            "predicted_next": round(predicted, 2),
            "trend_slope": round(slope, 4),
            "confidence": "low" if n < 5 else "medium" if n < 10 else "high",
            "model_info": self._current_model.get(metric, {}),
        }

    def handle_get_model(self, **kw: Any) -> dict[str, Any]:

        return {
            "model": self._current_model,
            "history_size": len(self._state_history),
            "tracked_metrics": list(self._current_model.keys()),
        }

    def handle_detect_state_transition(self, **kw: Any) -> dict[str, Any]:

        if len(self._state_history) < 5:
            return {"message": "Need at least 5 observations for transition detection"}

        transitions: list[dict[str, Any]] = []
        for key, info in self._current_model.items():
            if info.get("trend") in ("rising", "falling"):
                transitions.append({
                    "metric": key,
                    "transition": info["trend"],
                    "current": info.get("current"),
                    "baseline_mean": info.get("mean"),
                })

        return {
            "message": f"{len(transitions)} active transitions detected",
            "transitions": transitions,
        }
