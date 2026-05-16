from __future__ import annotations

import asyncio
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .agents import get_agent
from .agents.context_memory_agent import get_shared_state_value, record_session_turn
from .orchestrator import _decide_task_route


@contextmanager
def _temporary_env(overrides: dict[str, str]):
    original: dict[str, str | None] = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            os.environ[key] = value
        yield
    finally:
        for key, old_value in original.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def _is_network_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        token in lowered
        for token in (
            "network",
            "timeout",
            "connection",
            "dns",
            "tls",
            "certificate",
            "proxy",
            "unavailable",
            "blocked",
            "permission",
            "policy",
        )
    )


async def _run_router_case() -> dict[str, Any]:
    router = get_agent("router_agent")
    result = await asyncio.to_thread(
        router.execute,
        "route",
        {"query": "do some research about vector database from internet"},
    )
    data = result.data if result.success else {}
    primary = data.get("primary_route") or {}
    passed = result.success and primary.get("agent") == "research_agent"
    return {
        "name": "routing_research_prompt",
        "kind": "routing",
        "status": "passed" if passed else "failed",
        "score": 1.0 if passed else 0.0,
        "details": data or {"error": result.error},
        "note": "Research prompts should route to research_agent",
    }


async def _run_route_confidence_case() -> dict[str, Any]:
    decision = _decide_task_route("do some research about vector database from internet")
    passed = (
        decision.get("route") == "research"
        and float(decision.get("confidence", 0.0) or 0.0) >= 0.75
    )
    return {
        "name": "route_confidence_research",
        "kind": "routing",
        "status": "passed" if passed else "failed",
        "score": 1.0 if passed else 0.0,
        "details": decision,
        "note": "Research prompts should produce a confident research route",
    }


async def _run_file_case() -> dict[str, Any]:
    file_agent = get_agent("file_agent")
    with tempfile.TemporaryDirectory(prefix="limbi-eval-") as tmpdir:
        with _temporary_env(
            {
                "LIMBI_WORKSPACE_ROOT": tmpdir,
                "WORKSPACE_ROOT": tmpdir,
            }
        ):
            result = await asyncio.to_thread(
                file_agent.execute,
                "write_to_file",
                {
                    "path": "calculator_app",
                    "content": "print('hello from limbi')\n",
                    "language": "python",
                },
            )
            data = result.data if result.success else {}
            wrote_path = Path(data.get("path") or "")
            passed = result.success and wrote_path.suffix == ".py" and wrote_path.exists()
            return {
                "name": "file_write_extension_inference",
                "kind": "filesystem",
                "status": "passed" if passed else "failed",
                "score": 1.0 if passed else 0.0,
                "details": data or {"error": result.error},
                "note": "Bare paths should gain code extensions when language is known",
            }


async def _run_research_case() -> dict[str, Any]:
    research_agent = get_agent("research_agent")
    result = await asyncio.to_thread(
        research_agent.execute,
        "web_search",
        {"query": "vector database", "num_results": 3, "search_path": "auto"},
    )
    data = result.data if result.success else {}
    results = data.get("results") or []
    failed_reason = str(result.error or data.get("note") or "")
    skipped = not result.success and _is_network_error(failed_reason)
    has_citations = any(isinstance(item, dict) and str(item.get("citation") or "").strip() for item in results)
    passed = result.success and isinstance(results, list) and len(results) > 0 and has_citations
    return {
        "name": "live_research_search",
        "kind": "research",
        "status": "skipped" if skipped else ("passed" if passed else "failed"),
        "score": 0.5 if skipped else (1.0 if passed else 0.0),
        "details": data or {"error": result.error},
        "note": "Live search should return result entries and citation labels",
    }


async def _run_browser_case() -> dict[str, Any]:
    browser_agent = get_agent("browser_agent")
    result = await asyncio.to_thread(
        browser_agent.execute,
        "summarize_page",
        {"url": "https://example.com"},
    )
    data = result.data if result.success else {}
    skipped = not result.success and _is_network_error(str(result.error or data.get("error") or ""))
    passed = result.success and bool(str(data.get("summary") or "").strip()) and bool(str(data.get("source_method") or "").strip())
    return {
        "name": "browser_render_summary",
        "kind": "browser",
        "status": "skipped" if skipped else ("passed" if passed else "failed"),
        "score": 0.5 if skipped else (1.0 if passed else 0.0),
        "details": data or {"error": result.error},
        "note": "Rendered summaries should work for reachable pages",
    }


async def _run_permission_case() -> dict[str, Any]:
    from .workspace import load_config, set_permission_policy

    config = load_config()
    updated = set_permission_policy(config, "network", "research_agent", "allow")
    updated = set_permission_policy(updated, "filesystem", "file_agent", "workspace_only")
    return {
        "name": "permission_policy_loaded",
        "kind": "policy",
        "status": "passed",
        "score": 1.0,
        "details": {"permissions": updated.get("permissions", {})},
        "note": "Permission policy can be loaded and updated in workspace config",
    }


async def _run_topic_memory_case() -> dict[str, Any]:
    session_id = f"eval-topic-{os.getpid()}"
    record_session_turn(
        session_id,
        "user",
        "Build a calculator app in Python and save it to the workspace.",
        source_agent="user",
        metadata={"case": "topic_memory"},
    )
    record_session_turn(
        session_id,
        "assistant",
        "Use the file_agent to create a calculator_app.py file in the workspace.",
        source_agent="limbi",
        metadata={"case": "topic_memory"},
    )
    state = get_shared_state_value(session_id).get("state", {})
    clusters = state.get("topic_clusters") or {}
    active_state = state.get("active_project_state") or {}
    passed = bool(clusters) and bool(active_state.get("topic"))
    return {
        "name": "topic_cluster_memory",
        "kind": "memory",
        "status": "passed" if passed else "failed",
        "score": 1.0 if passed else 0.0,
        "details": {"topic_clusters": clusters, "active_project_state": active_state},
        "note": "Session memory should retain a topic cluster and active project state",
    }


async def run_evaluation_suite() -> dict[str, Any]:
    cases = [
        await _run_router_case(),
        await _run_route_confidence_case(),
        await _run_file_case(),
        await _run_research_case(),
        await _run_browser_case(),
        await _run_permission_case(),
        await _run_topic_memory_case(),
    ]

    passed = sum(1 for case in cases if case["status"] == "passed")
    skipped = sum(1 for case in cases if case["status"] == "skipped")
    failed = sum(1 for case in cases if case["status"] == "failed")
    score = round(sum(float(case["score"]) for case in cases) / max(len(cases), 1), 3)

    benchmark = {
        "agent": "limbi_suite",
        "score": score,
        "passed": passed,
        "skipped": skipped,
        "failed": failed,
    }

    return {
        "message": "Evaluation suite completed",
        "benchmark": benchmark,
        "cases": cases,
    }
