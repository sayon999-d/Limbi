from __future__ import annotations

import contextvars
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from .audit_log import (
    finish_prompt_trace,
    get_prompt_trace,
    get_recent_prompt_traces,
    init_db,
    log_trace_event,
    start_prompt_trace,
)

_CURRENT_TRACE_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "limbi_trace_id",
    default=None,
)
_TRACE_STARTED_AT: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "limbi_trace_started_at",
    default=None,
)


@dataclass
class TraceEvent:
    kind: str
    message: str = ""
    status: str = "info"
    agent: str = ""
    action: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class PromptTrace:
    trace_id: str
    session_id: str
    prompt: str
    provider: str = ""
    model: str = ""
    route: str = ""
    route_reason: str = ""
    route_confidence: float = 0.0
    status: str = "running"
    events: list[TraceEvent] = field(default_factory=list)
    start_ms: float = 0.0
    end_ms: float = 0.0
    duration_ms: float = 0.0


def current_trace_id() -> str | None:
    return _CURRENT_TRACE_ID.get()


def start_trace(
    *,
    session_id: str,
    prompt: str,
    provider: str = "",
    model: str = "",
    route: str = "",
    route_reason: str = "",
    route_confidence: float = 0.0,
) -> str:
    init_db()
    trace_id = str(uuid.uuid4())[:12]
    started_at = time.perf_counter()
    _CURRENT_TRACE_ID.set(trace_id)
    _TRACE_STARTED_AT.set(started_at)
    start_prompt_trace(
        trace_id=trace_id,
        session_id=session_id,
        prompt=prompt,
        provider=provider,
        model=model,
        route=route,
        route_reason=route_reason,
        route_confidence=route_confidence,
        start_ms=started_at * 1000,
    )
    log_trace_event(
        trace_id,
        kind="prompt.start",
        message="prompt received",
        payload={
            "session_id": session_id,
            "provider": provider,
            "model": model,
            "route": route,
            "route_reason": route_reason,
            "route_confidence": route_confidence,
        },
    )
    return trace_id


def record_trace_event(
    *,
    kind: str,
    message: str = "",
    status: str = "info",
    agent: str = "",
    action: str = "",
    payload: dict[str, Any] | None = None,
) -> int | None:
    trace_id = current_trace_id()
    if not trace_id:
        return None
    return log_trace_event(
        trace_id,
        kind=kind,
        message=message,
        status=status,
        agent=agent,
        action=action,
        payload=payload or {},
    )


def finish_trace(
    *,
    status: str = "completed",
    final_answer: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    search_path: str = "",
    research_source_count: int = 0,
) -> None:
    trace_id = current_trace_id()
    started_at = _TRACE_STARTED_AT.get()
    if not trace_id:
        return
    duration_ms = 0.0
    if started_at is not None:
        duration_ms = max(0.0, (time.perf_counter() - started_at) * 1000)
    finish_prompt_trace(
        trace_id,
        status=status,
        duration_ms=duration_ms,
        end_ms=time.perf_counter() * 1000,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        search_path=search_path,
        research_source_count=research_source_count,
        final_answer=final_answer,
    )
    log_trace_event(
        trace_id,
        kind="prompt.finish",
        message="prompt completed",
        status=status,
        payload={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "search_path": search_path,
            "research_source_count": research_source_count,
        },
    )
    _CURRENT_TRACE_ID.set(None)
    _TRACE_STARTED_AT.set(None)


@contextmanager
def trace_scope(**kwargs: Any) -> Iterator[str]:
    trace_id = start_trace(**kwargs)
    try:
        yield trace_id
    finally:
        if current_trace_id() == trace_id:
            finish_trace()


def get_trace(trace_id: str) -> dict[str, Any] | None:
    return get_prompt_trace(trace_id)


def list_traces(limit: int = 20) -> list[dict[str, Any]]:
    return get_recent_prompt_traces(limit=limit)
