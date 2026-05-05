from __future__ import annotations

import inspect
import json
import logging
import re
import sys
from typing import Any, get_args, get_origin

import limbi
from limbi.agents import get_agent, list_agents

logger = logging.getLogger("limbi.mcp")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "limbi-mcp", "version": limbi.__version__}


def tool_name_for(agent_name: str, action_name: str) -> str:
    return f"{agent_name}__{action_name}"


def _schema_from_annotation_text(annotation_text: str) -> dict[str, Any]:
    text = annotation_text.strip()
    if not text:
        return {"type": "string"}

    lowered = text.lower().replace(" ", "")
    if "|" in lowered:
        non_none_parts = [part for part in lowered.split("|") if part and part != "none"]
        if non_none_parts:
            return _schema_from_annotation_text(non_none_parts[0])

    if lowered in {"str", "builtins.str"}:
        return {"type": "string"}
    if lowered in {"int", "builtins.int"}:
        return {"type": "integer"}
    if lowered in {"float", "builtins.float"}:
        return {"type": "number"}
    if lowered in {"bool", "builtins.bool"}:
        return {"type": "boolean"}
    if lowered.startswith(("list[", "set[", "tuple[")) or lowered in {"list", "set", "tuple"}:
        return {"type": "array"}
    if lowered.startswith(("dict[", "mapping[")) or lowered in {"dict", "mapping"}:
        return {"type": "object"}
    if lowered in {"any", "typing.any"}:
        return {}
    if re.match(r"^(optional|sequence)\[", lowered):
        inner = lowered[lowered.find("[") + 1 : -1]
        return _schema_from_annotation_text(inner)
    return {"type": "string"}


def json_type_for(annotation: Any, default: Any) -> dict[str, Any]:
    if annotation is inspect._empty:
        annotation = type(default) if default not in (inspect._empty, None) else str

    if isinstance(annotation, str):
        return _schema_from_annotation_text(annotation)

    origin = get_origin(annotation)
    args = get_args(annotation)

    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    if origin is list or annotation is list:
        return {"type": "array"}
    if origin is dict or annotation is dict:
        return {"type": "object"}
    if origin is tuple:
        return {"type": "array"}
    if origin is not None and type(None) in args:
        filtered = [arg for arg in args if arg is not type(None)]
        return json_type_for(filtered[0], default) if filtered else {"type": "string"}
    return {"type": "string"}


def build_input_schema(handler) -> dict[str, Any]:
    signature = inspect.signature(handler)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in signature.parameters.items():
        if name == "self" or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        schema = json_type_for(param.annotation, param.default)
        if param.default is not inspect._empty and param.default is not None:
            schema["default"] = param.default
        properties[name] = schema

        if param.default is inspect._empty:
            required.append(name)

    result: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": True,
    }
    if required:
        result["required"] = required
    return result


def build_tools() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = [
        {
            "name": "limbi_health",
            "description": "Return Limbi backend and registry health information.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "limbi_list_agents",
            "description": "List all registered Limbi agents and their actions.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "limbi_route_query",
            "description": "Use the Limbi router agent to classify and route a natural-language query.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 3},
                },
                "required": ["query"],
                "additionalProperties": True,
            },
        },
    ]

    for agent_name, actions in sorted(list_agents().items()):
        agent = get_agent(agent_name)
        for action in actions:
            handler = getattr(agent, f"handle_{action}", None)
            description = (
                inspect.getdoc(handler).splitlines()[0]
                if inspect.getdoc(handler)
                else f"Run {agent_name}.{action}"
            )
            tools.append(
                {
                    "name": tool_name_for(agent_name, action),
                    "description": description,
                    "inputSchema": build_input_schema(handler)
                    if handler
                    else {"type": "object", "properties": {}, "additionalProperties": True},
                }
            )
    return tools


TOOLS = build_tools()


def call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    arguments = arguments or {}

    if name == "limbi_health":
        payload = {
            "agent_count": len(list_agents()),
            "agents": sorted(list(list_agents().keys())),
            "server": SERVER_INFO,
            "protocol_version": PROTOCOL_VERSION,
        }
        return success_result(payload)

    if name == "limbi_list_agents":
        payload = {
            "agents": {
                agent_name: actions
                for agent_name, actions in sorted(list_agents().items())
            }
        }
        return success_result(payload)

    if name == "limbi_route_query":
        router = get_agent("router_agent")
        result = router.execute(
            "route",
            {"query": arguments.get("query", ""), "top_k": arguments.get("top_k", 3)},
        )
        return agent_result(result.to_dict())

    if "__" not in name:
        return error_result({"error": f"Unknown tool '{name}'"})

    agent_name, action_name = name.split("__", 1)
    result = get_agent(agent_name).execute(action_name, arguments)
    return agent_result(result.to_dict())


def success_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
        "structuredContent": payload,
        "isError": False,
    }


def error_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
        "structuredContent": payload,
        "isError": True,
    }


def agent_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
        "structuredContent": payload,
        "isError": not payload.get("success", False),
    }


def response(message_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def error_response(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def write_message(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method", "")
    message_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        return response(
            message_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return response(message_id, {})

    if method == "tools/list":
        return response(message_id, {"tools": TOOLS})

    if method == "tools/call":
        try:
            result = call_tool(params.get("name", ""), params.get("arguments", {}))
            return response(message_id, result)
        except Exception as exc:
            logger.exception("Tool call failed")
            return response(message_id, error_result({"error": "Tool execution failed"}))

    return error_response(message_id, -32601, f"Method not found: {method}")


def main_loop() -> int:
    if sys.stdin.isatty():
        sys.stderr.write(
            "Limbi MCP server is running on stdio and waiting for MCP JSON-RPC input.\n"
            "This command is usually launched by an MCP client from .vscode/mcp.json.\n"
            "Press Ctrl+C to stop it.\n"
        )
        sys.stderr.flush()

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            write_message(error_response(None, -32700, "Parse error"))
            continue

        if isinstance(message, list):
            for item in message:
                result = handle_request(item)
                if result is not None:
                    write_message(result)
            continue

        result = handle_request(message)
        if result is not None:
            write_message(result)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main_loop())
    except KeyboardInterrupt:
        if sys.stdin.isatty():
            sys.stderr.write("\nLimbi MCP server stopped.\n")
            sys.stderr.flush()
        raise SystemExit(130)
