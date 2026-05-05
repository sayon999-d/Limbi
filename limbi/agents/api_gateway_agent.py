from __future__ import annotations

import logging
import time
from typing import Any

from . import BaseAgent

logger = logging.getLogger("limbi.agents.api_gateway")


class APIGatewayAgent(BaseAgent):

    agent_name = "api_gateway_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "api_gateway", "status": "ready", "capabilities": ["configure_route", "rate_limit_config", "cors_config", "auth_config", "health_status"]}

    def handle_configure_route(self, path: str = "", upstream: str = "", methods: list[str] | None = None, strip_prefix: bool = True, **kw: Any) -> dict[str, Any]:
        if not path or not upstream:
            raise ValueError("Both 'path' and 'upstream' are required")
        methods = methods or ["GET", "POST", "PUT", "DELETE"]
        return {"message": f"Route configured: {path} -> {upstream}", "route": {"path": path, "upstream": upstream, "methods": methods, "strip_prefix": strip_prefix}}

    def handle_rate_limit_config(self, endpoint: str = "", requests_per_minute: int = 60, burst: int = 10, **kw: Any) -> dict[str, Any]:
        if not endpoint:
            raise ValueError("'endpoint' is required")
        return {"message": f"Rate limit set: {endpoint} -> {requests_per_minute} req/min", "config": {"endpoint": endpoint, "requests_per_minute": requests_per_minute, "burst": burst, "algorithm": "token_bucket"}}

    def handle_cors_config(self, origins: list[str] | None = None, methods: list[str] | None = None, headers: list[str] | None = None, max_age: int = 3600, **kw: Any) -> dict[str, Any]:
        origins = origins or ["*"]
        methods = methods or ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        headers = headers or ["Content-Type", "Authorization"]
        return {"message": "CORS configured", "cors": {"origins": origins, "methods": methods, "headers": headers, "max_age": max_age, "credentials": origins != ["*"]}}

    def handle_auth_config(self, auth_type: str = "jwt", issuer: str = "", audience: str = "", **kw: Any) -> dict[str, Any]:
        configs = {
            "jwt": {"type": "jwt", "issuer": issuer or "https://auth.example.com", "audience": audience or "api", "algorithm": "RS256"},
            "api_key": {"type": "api_key", "header": "X-API-Key", "validation": "database_lookup"},
            "oauth2": {"type": "oauth2", "provider": issuer or "https://accounts.google.com", "scopes": ["read", "write"]},
        }
        return {"message": f"Auth configured: {auth_type}", "auth": configs.get(auth_type, configs["jwt"])}

    def handle_health_status(self, upstreams: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        upstreams = upstreams or ["api:8000", "auth:8001", "worker:8002"]
        status = [{"upstream": u, "status": "healthy", "latency_ms": 12 + i * 5, "last_check": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} for i, u in enumerate(upstreams)]
        return {"message": f"Gateway health: {len(upstreams)} upstreams", "upstreams": status, "all_healthy": True}
