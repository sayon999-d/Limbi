from __future__ import annotations

from typing import Any


def estimate_token_count(text: str) -> int:
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_usage_metadata(response: Any, prompt_text: str = "", completion_text: str = "") -> dict[str, int]:
    usage: dict[str, int] = {}

    usage_metadata = getattr(response, "usage_metadata", None)
    if isinstance(usage_metadata, dict):
        prompt_tokens = _coerce_int(
            usage_metadata.get("input_tokens")
            or usage_metadata.get("prompt_tokens")
        )
        completion_tokens = _coerce_int(
            usage_metadata.get("output_tokens")
            or usage_metadata.get("completion_tokens")
        )
        total_tokens = _coerce_int(usage_metadata.get("total_tokens"))
        if prompt_tokens is not None:
            usage["prompt_tokens"] = prompt_tokens
        if completion_tokens is not None:
            usage["completion_tokens"] = completion_tokens
        if total_tokens is not None:
            usage["total_tokens"] = total_tokens

    response_metadata = getattr(response, "response_metadata", None)
    if isinstance(response_metadata, dict):
        token_usage = response_metadata.get("token_usage") or response_metadata.get("usage")
        if isinstance(token_usage, dict):
            prompt_tokens = _coerce_int(
                token_usage.get("prompt_tokens")
                or token_usage.get("input_tokens")
            )
            completion_tokens = _coerce_int(
                token_usage.get("completion_tokens")
                or token_usage.get("output_tokens")
            )
            total_tokens = _coerce_int(token_usage.get("total_tokens"))
            if prompt_tokens is not None:
                usage.setdefault("prompt_tokens", prompt_tokens)
            if completion_tokens is not None:
                usage.setdefault("completion_tokens", completion_tokens)
            if total_tokens is not None:
                usage.setdefault("total_tokens", total_tokens)

    if "prompt_tokens" not in usage:
        usage["prompt_tokens"] = estimate_token_count(prompt_text)
    if "completion_tokens" not in usage:
        usage["completion_tokens"] = estimate_token_count(completion_text)
    if "total_tokens" not in usage:
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

    return usage


def estimate_hallucination_risk(
    *,
    prompt_text: str,
    raw_text: str,
    parsed_errors: list[str] | None = None,
    delegations: list[dict[str, Any]] | None = None,
    clarification_requested: bool = False,
) -> int:
    risk = 12
    errors = parsed_errors or []
    steps = delegations or []

    risk += min(40, len(errors) * 12)
    if clarification_requested:
        risk += 4
    if not raw_text.strip():
        risk += 18
    if prompt_text and len(prompt_text.split()) > 40 and len(raw_text.split()) < 20:
        risk += 8
    if steps and any(not step.get("success", True) for step in steps):
        risk += 8

    return max(0, min(100, risk))


def build_runtime_metrics(
    *,
    response: Any,
    prompt_text: str,
    raw_text: str,
    parsed_errors: list[str] | None = None,
    delegations: list[dict[str, Any]] | None = None,
    elapsed_ms: float = 0.0,
    clarification_requested: bool = False,
    task_complexity: str = "moderate",
    token_budget: int = 0,
    memory_turns: int = 0,
    task_route: str = "",
    route_confidence: float = 0.0,
    route_reason: str = "",
    search_path: str = "",
    research_source_count: int = 0,
    recommended_model: str = "",
    effective_model: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    usage = extract_usage_metadata(response, prompt_text=prompt_text, completion_text=raw_text)
    risk = estimate_hallucination_risk(
        prompt_text=prompt_text,
        raw_text=raw_text,
        parsed_errors=parsed_errors,
        delegations=delegations,
        clarification_requested=clarification_requested,
    )
    return {
        "latency_ms": round(elapsed_ms, 1),
        "latency_s": round(elapsed_ms / 1000.0, 2),
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "total_tokens": usage["total_tokens"],
        "task_complexity": task_complexity,
        "runtime_token_budget": token_budget,
        "memory_turns": memory_turns,
        "task_route": task_route,
        "route_confidence": round(route_confidence, 2),
        "route_reason": route_reason,
        "search_path": search_path,
        "research_source_count": research_source_count,
        "recommended_model": recommended_model,
        "effective_model": effective_model or recommended_model,
        "trace_id": trace_id,
        "estimated_hallucination_risk_percent": risk,
        "estimated_confidence_percent": 100 - risk,
    }
