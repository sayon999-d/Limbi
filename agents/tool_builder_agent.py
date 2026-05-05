

from __future__ import annotations

import json
import re
from typing import Any

from agents import BaseAgent

class ToolBuilderAgent(BaseAgent):

    agent_name = "tool_builder_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "tool_builder",
            "status": "ready",
            "capabilities": [
                "generate_tool_spec",
                "generate_openapi_tool",
                "scaffold_function",
                "validate_tool_contract",
                "list_tool_patterns",
            ],
        }

    def handle_generate_tool_spec(
        self,
        name: str = "",
        purpose: str = "",
        inputs: list[dict[str, str]] | None = None,
        outputs: list[dict[str, str]] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:
        if not name or not purpose:
            raise ValueError("'name' and 'purpose' are required")

        spec = {
            "name": self._slug(name),
            "purpose": purpose,
            "input_schema": inputs or [{"name": "input", "type": "string", "required": "true"}],
            "output_schema": outputs or [{"name": "result", "type": "object"}],
            "safety_notes": [
                "Validate all user inputs",
                "Return structured errors",
                "Avoid side effects unless explicitly requested",
            ],
        }
        return {"message": f"Generated tool spec for {name}", "spec": spec}

    def handle_generate_openapi_tool(self, name: str = "", endpoint: str = "", method: str = "POST", **kw: Any) -> dict[str, Any]:
        if not name or not endpoint:
            raise ValueError("'name' and 'endpoint' are required")

        schema = {
            "openapi": "3.1.0",
            "info": {"title": name, "version": "1.0.0"},
            "paths": {
                endpoint: {
                    method.lower(): {
                        "summary": f"{name} tool",
                        "responses": {"200": {"description": "Successful tool execution"}},
                    }
                }
            },
        }
        return {"message": f"Generated OpenAPI stub for {name}", "openapi": schema}

    def handle_scaffold_function(self, tool_name: str = "", language: str = "python", **kw: Any) -> dict[str, Any]:
        if not tool_name:
            raise ValueError("'tool_name' is required")

        fn = self._slug(tool_name).replace("-", "_")
        if language.lower() == "python":
            code = (
                f"def {fn}(params: dict) -> dict:\n"
                f"    \"\"\"Execute the {tool_name} tool.\"\"\"\n"
                f"    return {{\"success\": True, \"tool\": \"{fn}\", \"params\": params}}\n"
            )
        else:
            code = (
                f"function {fn}(params) {{\n"
                f"  return {{ success: true, tool: '{fn}', params }};\n"
                f"}}\n"
            )

        return {"message": f"Scaffolded {language} function for {tool_name}", "code": code}

    def handle_validate_tool_contract(self, contract_json: str = "", **kw: Any) -> dict[str, Any]:
        if not contract_json:
            raise ValueError("'contract_json' is required")

        try:
            contract = json.loads(contract_json)
        except json.JSONDecodeError as exc:
            return {"message": "Tool contract is invalid JSON", "valid": False, "error": str(exc)}

        required = ["name", "purpose"]
        missing = [key for key in required if key not in contract]
        return {
            "message": "Tool contract validated" if not missing else "Tool contract missing fields",
            "valid": not missing,
            "missing_fields": missing,
            "normalized_name": self._slug(contract.get("name", "")) if contract.get("name") else "",
        }

    def handle_list_tool_patterns(self, **kw: Any) -> dict[str, Any]:
        return {
            "message": "Returned common tool patterns",
            "patterns": [
                {"pattern": "lookup", "best_for": "read-only factual retrieval"},
                {"pattern": "transform", "best_for": "convert one structured payload into another"},
                {"pattern": "execute", "best_for": "side-effectful actions with explicit approvals"},
                {"pattern": "analyze", "best_for": "scoring, validation, or inspection"},
            ],
        }

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
