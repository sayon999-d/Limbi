from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .workspace import (
    PERMISSIONS_CONFIG_KEY,
    get_permission_policy as _get_permission_policy,
    set_permission_policy as _set_permission_policy,
)


@dataclass(frozen=True)
class PermissionDecision:
    scope: str
    actor: str
    action: str
    mode: str
    allowed: bool
    reason: str = ""


def get_permission_policy(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return _get_permission_policy(config or {})


def set_permission_policy(
    config: dict[str, Any],
    scope: str,
    actor: str,
    mode: str,
) -> dict[str, Any]:
    return _set_permission_policy(config, scope, actor, mode)


def _normalize_mode(mode: str | None) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized in {"allow", "allowed", "yes", "y", "on", "true"}:
        return "allow"
    if normalized in {"deny", "denied", "no", "n", "off", "false"}:
        return "deny"
    if normalized in {"approval_required", "prompt", "ask", "confirm"}:
        return "approval_required"
    if normalized in {"workspace_only", "workspace", "trust_workspace"}:
        return "workspace_only"
    return normalized or "allow"


def evaluate_permission(
    config: dict[str, Any] | None,
    scope: str,
    actor: str,
    action: str = "",
) -> PermissionDecision:
    policy = get_permission_policy(config or {})
    scope_key = str(scope or "").strip().lower()
    actor_key = str(actor or "").strip().lower()
    action_key = str(action or "").strip().lower()

    scope_policy = policy.get(scope_key, {})
    if not isinstance(scope_policy, dict):
        scope_policy = {}

    mode = _normalize_mode(scope_policy.get(actor_key) or scope_policy.get("default"))
    if scope_key == "filesystem" and mode == "allow":
        mode = "workspace_only"

    allowed = mode != "deny"
    if mode == "approval_required":
        allowed = False
    if mode == "workspace_only" and scope_key == "filesystem":
        allowed = True

    reason = ""
    if not allowed:
        reason = f"{scope_key}:{actor_key}:{action_key} is blocked by workspace policy ({mode})"
    elif mode == "approval_required":
        reason = f"{scope_key}:{actor_key}:{action_key} requires approval"

    return PermissionDecision(
        scope=scope_key,
        actor=actor_key,
        action=action_key,
        mode=mode,
        allowed=allowed,
        reason=reason,
    )


def require_permission(
    config: dict[str, Any] | None,
    scope: str,
    actor: str,
    action: str = "",
) -> None:
    decision = evaluate_permission(config, scope, actor, action)
    if not decision.allowed:
        raise PermissionError(
            decision.reason
            or f"{decision.scope}:{decision.actor}:{decision.action} is not allowed"
        )

