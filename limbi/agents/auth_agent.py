from __future__ import annotations

import os
import re
from typing import Any

from . import BaseAgent

class AuthAgent(BaseAgent):
    agent_name = "auth_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "auth_security",
            "status": "ready",
            "capabilities": [
                "review_auth_flow",
                "validate_token_format",
                "generate_rbac_matrix",
                "scan_auth_config",
                "plan_secret_rotation",
            ],
        }

    def handle_review_auth_flow(self, app_type: str = "", users: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        if not app_type:
            raise ValueError("'app_type' is required")

        recommendation = "OIDC with short-lived access tokens and refresh token rotation"
        if "service" in app_type.lower():
            recommendation = "machine-to-machine OAuth client credentials or signed service tokens"
        return {
            "message": f"Reviewed auth flow for {app_type}",
            "recommended_pattern": recommendation,
            "user_types": users or ["end_user"],
            "guardrails": ["least privilege", "token expiry", "centralized audit log"],
        }

    def handle_validate_token_format(self, token: str = "", **kw: Any) -> dict[str, Any]:
        if not token:
            raise ValueError("'token' is required")

        parts = token.split(".")
        token_type = "jwt" if len(parts) == 3 else "opaque"
        looks_base64 = all(re.fullmatch(r"[A-Za-z0-9_-]+", part or "") for part in parts[:3]) if token_type == "jwt" else False
        return {
            "message": "Validated token shape",
            "token_type": token_type,
            "structurally_valid": looks_base64 if token_type == "jwt" else len(token) >= 16,
            "parts": len(parts),
            "note": "Shape validation only; signature and claims are not verified by this action",
        }

    def handle_generate_rbac_matrix(self, roles: list[str] | None = None, resources: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        roles = roles or ["admin", "editor", "viewer"]
        resources = resources or ["projects", "settings", "reports"]
        matrix = []
        for role in roles:
            permissions = []
            for resource in resources:
                allowed = ["read"] if role == "viewer" else ["read", "write"]
                if role == "admin":
                    allowed.append("delete")
                permissions.append({"resource": resource, "allowed": allowed})
            matrix.append({"role": role, "permissions": permissions})
        return {"message": "Generated RBAC matrix", "matrix": matrix}

    def handle_scan_auth_config(self, env_prefixes: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        env_prefixes = env_prefixes or ["AUTH_", "JWT_", "OIDC_", "OAUTH_", "SESSION_"]
        found = []
        for key in os.environ:
            if any(key.startswith(prefix) for prefix in env_prefixes):
                found.append(key)
        return {
            "message": "Scanned auth-related configuration keys",
            "keys_found": sorted(found),
            "count": len(found),
            "note": "Only key names are returned, never secret values",
        }

    def handle_plan_secret_rotation(self, secret_names: list[str] | None = None, window_days: int = 30, **kw: Any) -> dict[str, Any]:
        secret_names = secret_names or ["api_key", "db_password", "signing_key"]
        steps = [
            "Create replacement secret",
            "Deploy systems that can read both old and new secrets",
            "Switch traffic to the new secret",
            "Revoke the old secret and confirm logs are clean",
        ]
        return {
            "message": "Planned secret rotation",
            "window_days": window_days,
            "secrets": secret_names,
            "steps": steps,
        }
