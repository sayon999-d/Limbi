from __future__ import annotations

import logging
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.feature_flag")

_flags: dict[str, dict[str, Any]] = {}


class FeatureFlagAgent(BaseAgent):

    agent_name = "feature_flag_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "feature_flags", "status": "ready", "active_flags": len([f for f in _flags.values() if f["enabled"]]), "total_flags": len(_flags), "capabilities": ["create_flag", "toggle_flag", "list_flags", "create_experiment", "evaluate_flag"]}

    def handle_create_flag(self, name: str = "", description: str = "", enabled: bool = False, rollout_pct: int = 0, **kw: Any) -> dict[str, Any]:
        if not name:
            raise ValueError("Flag 'name' is required")
        _flags[name] = {"name": name, "description": description, "enabled": enabled, "rollout_pct": rollout_pct, "variants": {"control": 100 - rollout_pct, "treatment": rollout_pct}}
        return {"message": f"Feature flag '{name}' created (enabled={enabled}, rollout={rollout_pct}%)", "flag": _flags[name]}

    def handle_toggle_flag(self, name: str = "", enabled: bool | None = None, **kw: Any) -> dict[str, Any]:
        if not name or name not in _flags:
            return {"message": f"Flag '{name}' not found", "available_flags": list(_flags.keys())}
        if enabled is not None:
            _flags[name]["enabled"] = enabled
        else:
            _flags[name]["enabled"] = not _flags[name]["enabled"]
        return {"message": f"Flag '{name}' toggled to {_flags[name]['enabled']}", "flag": _flags[name]}

    def handle_list_flags(self, **kw: Any) -> dict[str, Any]:
        return {"message": f"{len(_flags)} feature flags", "flags": list(_flags.values()), "active": len([f for f in _flags.values() if f["enabled"]])}

    def handle_create_experiment(self, name: str = "", hypothesis: str = "", metric: str = "", variants: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        if not name:
            raise ValueError("Experiment 'name' is required")
        variants = variants or [{"name": "control", "weight": 50}, {"name": "treatment", "weight": 50}]
        return {"message": f"A/B experiment '{name}' created", "experiment": {"name": name, "hypothesis": hypothesis, "primary_metric": metric, "variants": variants, "status": "draft"}}

    def handle_evaluate_flag(self, name: str = "", user_id: str = "", **kw: Any) -> dict[str, Any]:
        if not name:
            raise ValueError("Flag 'name' is required")
        flag = _flags.get(name)
        if not flag:
            return {"enabled": False, "reason": "flag_not_found"}
        if not flag["enabled"]:
            return {"enabled": False, "variant": "control", "reason": "flag_disabled"}
        user_hash = hash(user_id or "anonymous") % 100
        in_rollout = user_hash < flag["rollout_pct"]
        return {"enabled": in_rollout, "variant": "treatment" if in_rollout else "control", "user_id": user_id, "flag": name}
