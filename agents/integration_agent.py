

from __future__ import annotations

from typing import Any

from agents import BaseAgent

class IntegrationAgent(BaseAgent):

    agent_name = "integration_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "integration",
            "status": "ready",
            "capabilities": [
                "design_integration",
                "build_webhook_payload",
                "map_fields",
                "auth_header_template",
                "diagnose_integration",
            ],
        }

    def handle_design_integration(self, system_a: str = "", system_b: str = "", trigger: str = "", **kw: Any) -> dict[str, Any]:
        if not system_a or not system_b:
            raise ValueError("'system_a' and 'system_b' are required")

        flow = [
            f"{system_a} emits event or is polled",
            "Integration layer validates and normalizes payload",
            f"{system_b} receives mapped request",
            "Result is logged with retry and dead-letter handling",
        ]
        return {
            "message": f"Designed integration between {system_a} and {system_b}",
            "trigger": trigger or "event_or_schedule",
            "flow": flow,
            "reliability_controls": ["idempotency key", "retry policy", "audit log"],
        }

    def handle_build_webhook_payload(self, event_name: str = "", fields: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        if not event_name:
            raise ValueError("'event_name' is required")

        payload = {"event": event_name, "timestamp": "<iso8601>", "data": {field: f"<{field}>" for field in (fields or ["id", "status"])}}
        return {"message": f"Built webhook payload for {event_name}", "payload": payload}

    def handle_map_fields(self, source_fields: list[str] | None = None, target_fields: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        source_fields = source_fields or []
        target_fields = target_fields or []
        mapping = []
        for idx, target in enumerate(target_fields):
            source = source_fields[idx] if idx < len(source_fields) else ""
            mapping.append({"source": source, "target": target, "status": "mapped" if source else "missing_source"})
        return {"message": "Generated field mapping", "mapping": mapping}

    def handle_auth_header_template(self, auth_type: str = "bearer", **kw: Any) -> dict[str, Any]:
        auth_type = auth_type.lower()
        if auth_type == "api_key":
            headers = {"X-API-Key": "<api_key>"}
        elif auth_type == "basic":
            headers = {"Authorization": "Basic <base64(username:password)>"}
        else:
            headers = {"Authorization": "Bearer <token>"}
        return {"message": f"Generated auth header template for {auth_type}", "headers": headers}

    def handle_diagnose_integration(self, symptoms: str = "", **kw: Any) -> dict[str, Any]:
        if not symptoms:
            raise ValueError("'symptoms' is required")

        symptoms_lower = symptoms.lower()
        likely = []
        if "401" in symptoms_lower or "auth" in symptoms_lower:
            likely.append("credentials_or_token_issue")
        if "429" in symptoms_lower or "rate" in symptoms_lower:
            likely.append("rate_limit_or_retry_policy")
        if "timeout" in symptoms_lower or "slow" in symptoms_lower:
            likely.append("upstream_latency_or_network_instability")
        if "schema" in symptoms_lower or "payload" in symptoms_lower:
            likely.append("field_mapping_or_contract_drift")
        return {
            "message": "Diagnosed likely integration failure modes",
            "symptoms": symptoms,
            "likely_causes": likely or ["insufficient_signal"],
            "next_checks": ["inspect request/response logs", "validate auth", "compare payload with contract"],
        }
