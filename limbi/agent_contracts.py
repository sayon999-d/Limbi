from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, get_args, get_origin


@dataclass(frozen=True)
class ActionContract:
    agent: str
    action: str
    input_schema: dict[str, Any]
    required: list[str] = field(default_factory=list)
    allows_extra: bool = True
    description: str = ""


def _annotation_to_schema(annotation: Any, default: Any = inspect._empty) -> dict[str, Any]:
    if annotation is inspect._empty:
        if default is not inspect._empty and default is not None:
            return _annotation_to_schema(type(default), inspect._empty)
        return {"type": "string"}

    if isinstance(annotation, str):
        text = annotation.strip().lower().replace(" ", "")
        if "|" in text:
            parts = [part for part in text.split("|") if part and part != "none"]
            if parts:
                return _annotation_to_schema(parts[0], inspect._empty)
        if text in {"str", "builtins.str"}:
            return {"type": "string"}
        if text in {"int", "builtins.int"}:
            return {"type": "integer"}
        if text in {"float", "builtins.float"}:
            return {"type": "number"}
        if text in {"bool", "builtins.bool"}:
            return {"type": "boolean"}
        if text in {"list", "tuple", "set"} or text.startswith(("list[", "tuple[", "set[")):
            return {"type": "array"}
        if text in {"dict", "mapping"} or text.startswith(("dict[", "mapping[")):
            return {"type": "object"}
        if text.startswith(("optional[", "sequence[")):
            inner = text[text.find("[") + 1 : -1]
            return _annotation_to_schema(inner, inspect._empty)
        return {"type": "string"}

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
    if origin in {list, set, tuple} or annotation in {list, set, tuple}:
        return {"type": "array"}
    if origin in {dict,} or annotation is dict:
        return {"type": "object"}
    if origin is not None and type(None) in args:
        filtered = [arg for arg in args if arg is not type(None)]
        return _annotation_to_schema(filtered[0], inspect._empty) if filtered else {"type": "string"}
    return {"type": "string"}


def build_action_contract(agent_name: str, action_name: str, handler: Any) -> ActionContract:
    signature = inspect.signature(handler)
    properties: dict[str, Any] = {}
    required: list[str] = []
    allows_extra = False

    for name, param in signature.parameters.items():
        if name == "self":
            continue
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            allows_extra = True
            continue
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            continue

        schema = _annotation_to_schema(param.annotation, param.default)
        if param.default is not inspect._empty and param.default is not None:
            schema["default"] = param.default
        properties[name] = schema
        if param.default is inspect._empty:
            required.append(name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": allows_extra,
    }
    if required:
        schema["required"] = required

    return ActionContract(
        agent=agent_name,
        action=action_name,
        input_schema=schema,
        required=required,
        allows_extra=allows_extra,
        description=(inspect.getdoc(handler) or "").splitlines()[0] if inspect.getdoc(handler) else "",
    )


def _schema_type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True


def validate_action_params(handler: Any, params: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    signature = inspect.signature(handler)
    params = dict(params or {})
    errors: list[str] = []
    cleaned: dict[str, Any] = {}
    allows_extra = any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for name, param in signature.parameters.items()
        if name != "self"
    )

    for name, param in signature.parameters.items():
        if name == "self" or param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
            continue

        if name not in params:
            if param.default is inspect._empty:
                errors.append(f"Missing required parameter '{name}'")
            continue

        value = params.pop(name)
        schema = _annotation_to_schema(param.annotation, param.default)
        expected_type = schema.get("type")
        if expected_type and not _schema_type_matches(value, expected_type):
            errors.append(f"Parameter '{name}' must be of type {expected_type}")
            continue
        cleaned[name] = value

    if params:
        if allows_extra:
            cleaned.update(params)
        else:
            errors.append(f"Unexpected parameters: {', '.join(sorted(params))}")

    return cleaned, errors


def build_input_schema(handler: Any) -> dict[str, Any]:
    return build_action_contract("", "", handler).input_schema
