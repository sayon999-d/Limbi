

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from urllib.parse import urlparse
from typing import Any, AsyncIterator, Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from llm_provider import get_llm_provider, ProviderConfig, provider_requires_api_key

from payload_parser import ParsedOutput, parse_llm_output
from agents import get_agent, list_agents, AgentResult
from vector_store import VectorStore
from audit_log import log_execution, get_recent_executions
from agents.context_memory_agent import (
    publish_agent_result,
    get_session_context,
    record_session_turn,
    get_shared_state_value,
    set_shared_state_value,
)
from limbi.runtime_metrics import build_runtime_metrics
from limbi.permissions import evaluate_permission
from limbi.tracing import start_trace, record_trace_event, finish_trace
from limbi.workspace import load_config

logger = logging.getLogger("limbi.orchestrator")

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 0.5

MAX_HISTORY_MESSAGES = 24
SUMMARIZE_THRESHOLD = 16

SYSTEM_PROMPT = """\
You are **Limbi**, an elite full-stack AI assistant with access to a swarm \
of specialised agents that can execute real-world actions on behalf of the user.

## Your Capabilities
You can BOTH:
1. **Converse** - answer questions, explain code, write documentation, debug \
   problems, and provide expert guidance across all programming domains.
2. **Delegate** - trigger real-world actions by emitting structured JSON \
   delegation blocks that are dispatched to specialised agents.

## Available Agents & Actions
{agent_registry}

## Agent Naming Rules
- Use only exact agent names that appear in the registry above.
- Do not invent new agent names or generic placeholders.
- If you need a learning-related capability, use `learning_agent`.
- For `learning_agent`, use `get_best_action`, `get_insights`, `get_q_table`, or `record_feedback`.
- For `research_agent`, use `web_search`, `fetch_url`, `summarize`, `fact_check`, or `compare_sources`.
- If a requested capability is not registered, say so plainly and suggest the closest existing agent.
- When listing required or optional agents, keep the list limited to real registered agents only.

## Clarification Rules
- Ask clarifying questions only when the request is genuinely ambiguous and you cannot
  safely continue with sensible defaults.
- Prefer to act with the current workspace, current provider, and a reasonable stack
  choice when the user has already stated a concrete task.
- Do not interrupt a build, edit, or repair task just to ask for stack preferences
  unless the choice materially changes the work.
- If file paths, output targets, runtime targets, or provider details are missing and
  there is no safe default, ask a single focused question instead of multiple questions.
- If a needed capability is missing, use `mutation_agent` to propose a new agent only after the user approves.

## How Delegation Works
When you decide an action needs to be executed in the real world, include a \
**fenced JSON block** in your response:

```json
[
  {{"agent": "<agent_name>", "action": "<action_name>", "params": {{...}}}}
]
```

### Rules for Delegation
- You may include ZERO or MORE delegation blocks in a single response.
- Always explain to the user *what* you're doing and *why* alongside any blocks.
- If a delegation fails, you will receive the error. Explain it clearly and \
  suggest a fix.
- NEVER fabricate that an action succeeded - always wait for the actual result.
- You may combine conversation and delegation in the same message.
- If multiple independent actions are needed, put them ALL in a single JSON \
  array so they execute in parallel.

## Tone & Style
- Be concise but thorough. Use markdown formatting.
- When showing code, specify the language for syntax highlighting.
- Proactively suggest improvements and next steps.
- When referring to past actions, check the recent execution history below.
- Use the shared agent context to understand what other agents have already
  done in this session. This helps you avoid redundant work and build on
  earlier findings.

{recent_executions}

{shared_agent_context}

{rag_context}

## URL Research Context
{url_research_context}

## Internet Research Context
{web_research_context}

## Source Grounding Rules
- If URL research context is present, use it as the primary evidence source.
- If internet research context is present, use it as the primary evidence source.
- Prefer facts, headings, and quoted page content over generic memory.
- Cite source-backed claims inline with the source labels shown in the research context
  such as `[U1]` or `[W1]`.
- If sources disagree or evidence is incomplete, say so plainly instead of guessing.
- If a URL cannot be fetched or rendered, say so plainly and do not invent details.
- If the user asks for research, answer the topic directly from the research context and do not dump the agent registry unless the user asked about agents.
"""


def _needs_clarification(user_message: str) -> list[str]:
    text = user_message.lower().strip()
    words = text.split()

    task_verbs = {"build", "create", "make", "design", "write", "implement", "fix", "improve", "optimize", "generate"}
    vague_words = {"something", "stuff", "thing", "things", "whatever", "some", "it", "this", "that", "there", "here"}
    path_words = {"path", "file", "folder", "directory", "save", "write", "output"}
    explicit_targets = {
        "app", "project", "tool", "site", "api", "workflow", "agent",
        "calculator", "dashboard", "cli", "script", "page", "server",
        "component", "module", "service", "utility",
    }

    has_task = any(verb in text for verb in task_verbs)
    has_research_intent = _looks_like_web_research_prompt(user_message)
    has_explicit_target = any(word in text for word in explicit_targets)
    has_vague_language = any(word in text for word in vague_words)
    has_path_context = any(word in text for word in path_words)

    if has_research_intent and len(words) <= 14:
        return []

    if not has_task:
        if has_vague_language and len(words) <= 8:
            return ["What exactly would you like me to do?"]
        return []

    if len(words) <= 8 and not has_explicit_target:
        return ["What exact output should I create or change?"]

    if has_path_context and not has_explicit_target and len(words) <= 16:
        return ["Where should I place the output in the workspace?"]

    return []

def _build_agent_registry_text() -> str:

    agents = list_agents()
    if not agents:
        return "*(No agents currently registered)*"
    lines = ["| Agent | Available Actions |", "|-------|-------------------|"]
    for name, actions in agents.items():
        lines.append(f"| `{name}` | {', '.join(f'`{a}`' for a in actions)} |")
    return "\n".join(lines)

def _build_recent_executions_text() -> str:

    try:
        recent = get_recent_executions(limit=3)
    except Exception:
        return ""
    if not recent:
        return ""
    lines = ["## Recent Agent Executions"]
    for r in reversed(recent):
        status = "" if r.get("success") else ""
        lines.append(
            f"- {status} `{r['agent']}.{r['action']}` at {r['timestamp']}"
            f"{(' - ' + r['error']) if r.get('error') else ''}"
        )
    return "\n".join(lines)


def _compact_summary(existing: str, latest: str, *, limit: int = 1200) -> str:
    bullets: list[str] = []
    seen: set[str] = set()
    for block in (existing, latest):
        for raw_line in (block or "").splitlines():
            line = raw_line.strip().lstrip("-•*").strip()
            if not line:
                continue
            normalized = re.sub(r"\s+", " ", line).lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            bullets.append(f"- {line}")
    summary = "\n".join(bullets)
    if len(summary) > limit:
        summary = summary[: limit - 3].rstrip() + "..."
    return summary


def _looks_like_web_research_prompt(user_message: str) -> bool:
    text = user_message.lower()
    return any(
        token in text
        for token in (
            "research",
            "search the internet",
            "search internet",
            "look up",
            "find information",
            "from the internet",
            "online",
            "web search",
            "browse",
            "latest on",
            "current information",
        )
    )


def _extract_research_query(user_message: str) -> str:
    text = re.sub(r"https?://\S+", " ", user_message)
    patterns = [
        r"\bdo\s+some\s+research\s+about\b",
        r"\bresearch\s+about\b",
        r"\bresearch\s+on\b",
        r"\bresearch\b",
        r"\bsearch\s+the\s+internet\s+for\b",
        r"\bsearch\s+internet\s+for\b",
        r"\blook\s+up\b",
        r"\bfind\s+information\s+about\b",
        r"\bfind\s+information\s+on\b",
        r"\bfrom\s+the\s+internet\b",
        r"\bon\s+the\s+internet\b",
        r"\bonline\b",
        r"\bweb\s+search\b",
        r"\bbrowse\b",
    ]
    for pattern in patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[\-\:\,\.\?\!]+$", " ", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text or user_message.strip()


def _choose_web_search_path(user_message: str) -> str:
    text = user_message.lower()
    if any(token in text for token in ("duckduckgo", "ddg", "www.duckduckgo.com", "duckduckgo.com")):
        return "duckduckgo"
    if any(token in text for token in ("google.com", "www.google.com", "google search", "search google", "google")):
        return "google"
    return "auto"


def _emit_progress(
    progress_callback: Callable[[str], None] | None,
    message: str,
) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(message)
    except Exception:
        pass


def _extract_urls(text: str) -> list[str]:
    candidates = re.findall(r"https?://[^\s<>()\[\]{}]+", text)
    urls: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        cleaned = raw.rstrip(".,;:!?)]}'\"")
        parsed = urlparse(cleaned)
        if not parsed.scheme or not parsed.netloc:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        urls.append(cleaned)
    return urls


def _dedupe_history_messages(messages: list[HumanMessage | AIMessage], limit: int = 8) -> list[HumanMessage | AIMessage]:
    if limit <= 0 or not messages:
        return []
    recent = messages[-limit:]
    deduped: list[HumanMessage | AIMessage] = []
    seen: set[str] = set()
    for message in recent:
        content = str(getattr(message, "content", "") or "").strip()
        if not content:
            continue
        normalized = re.sub(r"\s+", " ", content).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(message)
    return deduped


def _looks_like_delegation_only(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return True
    markers = [
        "here is the delegation block",
        "delegation block",
        "agent execution results",
        "let's use the research_agent",
        "let us use the research_agent",
        "here's how you can use it",
    ]
    if any(marker in normalized for marker in markers):
        return True
    return len(normalized.split()) < 45


def _looks_like_internal_agent_dump(text: str) -> bool:
    normalized = (text or "").lower()
    markers = (
        "registered agent names",
        "agent registry",
        "available agents & actions",
        "here are some additional details",
        "use only exact agent names",
        "context_memory_agent",
        "mutation_agent",
    )
    return any(marker in normalized for marker in markers)


def _summarize_delegation_results(
    delegation_results: list[dict[str, Any]],
    user_message: str,
) -> str:
    if not delegation_results:
        return ""

    lines: list[str] = []
    research_entries: list[str] = []

    for result in delegation_results:
        agent = result.get("agent", "unknown")
        action = result.get("action", "unknown")
        data = result.get("data", {}) or {}
        message = data.get("message") or result.get("error") or "No message returned."

        if agent == "research_agent" and action in {"web_search", "find_information"}:
            results = data.get("results") or []
            titles: list[str] = []
            for item in results[:3]:
                if isinstance(item, dict):
                    title = str(item.get("title") or "").strip()
                    snippet = str(item.get("snippet") or "").strip()
                    url = str(item.get("url") or "").strip()
                    if title:
                        segment = title
                        if snippet:
                            segment += f": {snippet}"
                        elif url:
                            segment += f" ({url})"
                        titles.append(segment)
            if titles:
                research_entries.append("\n".join(f"- {item}" for item in titles))
                continue

        lines.append(f"- {agent}.{action}: {message}")

    summary_bits: list[str] = []
    if research_entries:
        summary_bits.append("Research summary:")
        summary_bits.extend(research_entries)

    if lines:
        if summary_bits:
            summary_bits.append("")
        summary_bits.append("Other delegated work:")
        summary_bits.extend(lines)

    if not summary_bits:
        summary_bits.append("The delegated tools completed, but they did not return a concise answer body.")

    return "\n".join(summary_bits).strip()


def _estimate_task_complexity(
    user_message: str,
    *,
    rag_context: str = "",
    url_research_context: str = "",
    web_research_context: str = "",
    shared_context: str = "",
) -> dict[str, Any]:
    text = user_message.lower()
    words = user_message.split()
    score = 0

    if len(words) > 18:
        score += min(4, len(words) // 18)
    if len(words) > 60:
        score += 2

    if any(token in text for token in ("build", "create", "implement", "refactor", "debug", "fix", "optimize", "design")):
        score += 2
    if any(token in text for token in ("research", "summarize", "compare", "analyze", "article", "website", "url", "source")):
        score += 2
    if _extract_urls(user_message):
        score += 2
    if any(token in text for token in ("file", "folder", "workspace", "save", "write", "agent", "model", "provider")):
        score += 1
    if "\n" in user_message or "```" in user_message:
        score += 1
    if text.count(" and ") >= 2 or text.count(",") >= 3:
        score += 1
    if rag_context:
        score += 1
    if url_research_context:
        score += 2
    if web_research_context:
        score += 2
    if shared_context:
        score += min(2, max(0, len(shared_context) // 800))

    if score <= 2:
        level = "simple"
    elif score <= 6:
        level = "moderate"
    else:
        level = "complex"

    return {"score": score, "level": level}


def _suggest_runtime_limits(level: str, base_max_tokens: int, base_temperature: float) -> dict[str, Any]:
    base_max_tokens = max(256, int(base_max_tokens or 1024))
    base_temperature = max(0.0, float(base_temperature or 0.1))

    if level == "simple":
        max_tokens = min(base_max_tokens, 512)
        temperature = min(base_temperature, 0.05)
    elif level == "complex":
        max_tokens = min(max(base_max_tokens, 1536), 2048)
        temperature = min(base_temperature, 0.1)
    else:
        max_tokens = min(max(base_max_tokens, 768), 1024)
        temperature = min(base_temperature, 0.08)

    return {
        "max_tokens": max_tokens,
        "temperature": round(temperature, 2),
    }


def _suggest_model_for_task(provider_name: str, task_route: str, task_level: str, current_model: str) -> str:
    provider_name = (provider_name or "").strip().lower()
    current_model = (current_model or "").strip()
    if provider_name not in {"ollama", "lmstudio", "vllm", "localai", "koboldcpp", "llamacpp", "ollama_cloud"}:
        return current_model
    if provider_name == "ollama_cloud":
        if task_route == "research" or task_level == "complex":
            return "deepseek-v3.1:671b-cloud"
        if task_route == "delegate":
            return "qwen3-coder:480b-cloud"
        return "gpt-oss:20b-cloud"
    if task_level == "simple":
        return "gemma2:2b"
    if task_route == "research":
        return "qwen2.5:3b"
    if task_route == "delegate":
        return "llama3.2:3b"
    return current_model or "llama3.2:3b"


def _decide_task_route(
    user_message: str,
    *,
    url_research_context: str = "",
    web_research_context: str = "",
    rag_context: str = "",
) -> dict[str, Any]:
    text = user_message.lower()
    route = "direct"
    reason = "general conversation"
    confidence = 0.55

    if _looks_like_web_research_prompt(user_message):
        confidence = 0.78
    if url_research_context or web_research_context:
        confidence = max(confidence, 0.9)

    if _needs_clarification(user_message) and not _looks_like_web_research_prompt(user_message):
        route = "clarify"
        reason = "request is ambiguous"
        confidence = 0.35
    elif _looks_like_web_research_prompt(user_message) or url_research_context or web_research_context:
        route = "research"
        reason = "research intent or research context detected"
        confidence = max(confidence, 0.88)
    elif any(token in text for token in ("build", "create", "implement", "refactor", "debug", "fix", "write", "save", "generate code")):
        route = "delegate"
        reason = "action-oriented build/edit task"
        confidence = 0.76
    elif rag_context:
        route = "retrieve"
        reason = "workspace context is relevant"
        confidence = 0.72

    return {"route": route, "reason": reason, "confidence": round(min(confidence, 0.98), 2)}

class Orchestrator:

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.3,
        session_id: str = "global",
    ) -> None:

        self._provider = get_llm_provider()
        self._model_name = self._provider.config.model

        self._history: list[HumanMessage | AIMessage] = []

        self._conversation_summary: str = ""
        self._current_goal: str = ""
        self._current_route: str = "direct"
        self._route_reason: str = ""
        self._route_confidence: float = 0.0
        self._recommended_model: str = ""
        self._search_path: str = ""

        self._vector_store = VectorStore()

        self._llm_cache: dict[tuple[Any, ...], BaseChatModel] = {}

        self._session_id = session_id

        try:
            saved_summary = get_shared_state_value(self._session_id, "conversation_summary").get("value")
            if isinstance(saved_summary, str):
                self._conversation_summary = saved_summary
        except Exception:
            pass

        logger.info(
            "Orchestrator init - provider=%s model=%s session=%s",
            self._provider.provider_name(),
            self._model_name,
            self._session_id,
        )

    def _ensure_llm(
        self,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        model_name: str | None = None,
    ) -> BaseChatModel:
        effective_model = (model_name or self._provider.config.model or "").strip()
        if not effective_model:
            effective_model = self._model_name
        runtime_config = ProviderConfig(
            provider=self._provider.config.provider,
            model=effective_model,
            base_url=self._provider.config.base_url,
            api_key=self._provider.config.api_key,
            temperature=self._provider.config.temperature if temperature is None else temperature,
            max_tokens=self._provider.config.max_tokens if max_tokens is None else max_tokens,
            azure_deployment=self._provider.config.azure_deployment,
            azure_api_version=self._provider.config.azure_api_version,
        )
        cache_key = (
            runtime_config.provider,
            runtime_config.model,
            runtime_config.base_url,
            runtime_config.api_key,
            runtime_config.temperature,
            runtime_config.max_tokens,
            runtime_config.azure_deployment,
            runtime_config.azure_api_version,
        )
        llm = self._llm_cache.get(cache_key)
        if llm is None:
            llm = get_llm_provider(runtime_config).get_chat_model()
            self._llm_cache[cache_key] = llm
        return llm

    def _sync_session_state(self) -> None:
        try:
            set_shared_state_value(self._session_id, "provider", self._provider.provider_name())
            set_shared_state_value(self._session_id, "model", self._provider.config.model)
            set_shared_state_value(self._session_id, "base_url", self._provider.config.base_url)
            set_shared_state_value(self._session_id, "workspace_path", str(Path.cwd().resolve()))
            set_shared_state_value(self._session_id, "active_project_root", str(Path.cwd().resolve()))
            set_shared_state_value(self._session_id, "current_goal", self._current_goal)
            set_shared_state_value(self._session_id, "current_focus", self._current_goal)
            set_shared_state_value(self._session_id, "current_route", self._current_route)
            set_shared_state_value(self._session_id, "route_reason", getattr(self, "_route_reason", ""))
            set_shared_state_value(self._session_id, "route_confidence", getattr(self, "_route_confidence", 0.0))
            set_shared_state_value(self._session_id, "recommended_model", self._recommended_model)
            set_shared_state_value(self._session_id, "search_path", self._search_path)
            if self._conversation_summary:
                set_shared_state_value(self._session_id, "conversation_summary", self._conversation_summary)
        except Exception as exc:
            logger.debug("Session state sync failed: %s", exc)

    def _record_turn(
        self,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        try:
            record_session_turn(
                self._session_id,
                role,
                content,
                source_agent="limbi" if role != "user" else "user",
                metadata=metadata or {},
                priority="high" if role == "user" else "normal",
            )
        except Exception as exc:
            logger.debug("Session turn record skipped: %s", exc)
        try:
            memory_agent = get_agent("memory_agent")
            memory_agent.execute(
                "note",
                {
                    "content": content[:2000],
                    "role": role,
                    "session_id": self._session_id,
                },
            )
        except Exception as exc:
            logger.debug("Short-term memory record skipped: %s", exc)

    async def _build_url_research_context(
        self,
        user_message: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> str:
        urls = _extract_urls(user_message)
        if not urls:
            return ""

        _emit_progress(progress_callback, "Searching sources")
        record_trace_event(
            kind="research.url",
            message="building URL research context",
            payload={"url_count": len(urls)},
        )

        try:
            web_agent = get_agent("web_scraping_agent")
        except KeyError:
            web_agent = None

        try:
            research_agent = get_agent("research_agent")
        except KeyError:
            research_agent = None

        async def summarize_url(url: str) -> dict[str, Any]:
            try:
                if web_agent is None:
                    return {
                        "url": url,
                        "title": "",
                        "section_headings": [],
                        "summary": "",
                        "error": "web_scraping_agent is not available",
                    }

                result = await asyncio.to_thread(web_agent.execute, "summarize_page", {"url": url})
                data = result.data if result.success else {}
                return {
                    "url": url,
                    "title": str(data.get("title") or urlparse(url).netloc or url),
                    "section_headings": list(data.get("section_headings") or []),
                    "summary": str(data.get("summary") or data.get("message") or ""),
                    "word_count": data.get("word_count", 0),
                    "success": result.success,
                    "error": result.error,
                }
            except Exception as exc:
                return {
                    "url": url,
                    "title": urlparse(url).netloc or url,
                    "section_headings": [],
                    "summary": "",
                    "success": False,
                    "error": str(exc),
                }

        source_summaries = await asyncio.gather(
            *(summarize_url(url) for url in urls[:3]),
            return_exceptions=False,
        )

        source_blocks: list[str] = ["## Fetched URL Sources"]
        comparison_sources: list[dict[str, str]] = []

        for index, item in enumerate(source_summaries, start=1):
            citation = f"[U{index}]"
            headings = item.get("section_headings") or []
            summary = item.get("summary") or ""
            excerpt = str(item.get("summary") or item.get("excerpt") or "").strip()
            quoted_evidence = str(item.get("quoted_evidence") or excerpt).strip()
            source_blocks.append(
                "\n".join(
                    [
                        f"### Source {index} {citation}",
                        f"- URL: {item['url']}",
                        f"- Title: {item.get('title') or '(unknown)'}",
                        f"- Status: {'fetched' if item.get('success') else 'unavailable'}",
                        f"- Citation: {citation}",
                        f"- Key headings: {', '.join(headings[:5]) if headings else '(none)'}",
                        f"- Summary: {summary[:1200] if summary else '(no summary available)'}",
                        f"- Evidence excerpt: {excerpt[:300] if excerpt else '(none)'}",
                        f"- Quoted evidence: {quoted_evidence[:300] if quoted_evidence else '(none)'}",
                    ]
                )
            )
            if summary:
                comparison_sources.append(
                    {
                        "title": f"{item.get('title') or f'Source {index}'} {citation}",
                        "content": f"URL: {item['url']}\n{summary}",
                        "citation": citation,
                    }
                )

        if research_agent is not None and len(comparison_sources) >= 2:
            compare_result = await asyncio.to_thread(
                research_agent.execute,
                "compare_sources",
                {"sources": comparison_sources, "topic": user_message[:200]},
            )
            compare_data = compare_result.data if compare_result.success else {}
            source_blocks.append(
                "\n".join(
                    [
                        "### Source Comparison",
                        f"- Consensus: {compare_data.get('consensus', 'unknown')}",
                        f"- Agreement ratio: {compare_data.get('agreement_ratio', 0)}",
                        f"- Common themes: {', '.join(compare_data.get('common_themes', [])[:8]) or '(none)'}",
                        f"- Disagreements: {', '.join(compare_data.get('disagreements', [])[:4]) or '(none)'}",
                    ]
                )
            )
            if str(compare_data.get("consensus", "")).lower() == "weak":
                source_blocks.append("### Confidence Note\n- The sources disagree enough that a cautious answer should say 'I don't know' or note uncertainty.")
        elif len(comparison_sources) >= 2:
            source_blocks.append(
                "### Source Comparison\n- Consensus: unavailable\n- Agreement ratio: unavailable\n- Common themes: unavailable"
            )

        record_trace_event(
            kind="research.url",
            message="URL research context built",
            payload={"url_count": len(source_summaries), "comparison_count": len(comparison_sources)},
        )

        source_blocks.append(
            "## How To Use These Sources\n"
            "- Treat the fetched material as the primary evidence.\n"
            "- If the answer depends on details not visible in the fetched pages, say so.\n"
            "- Prefer source-based summaries over generic model memory.\n"
            "- Cite important claims with the reference labels like [U1], [U2]."
        )
        return "\n\n".join(source_blocks)

    async def _build_web_research_context(
        self,
        user_message: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> str:
        if _extract_urls(user_message):
            return ""
        if not _looks_like_web_research_prompt(user_message):
            return ""

        query = _extract_research_query(user_message)
        search_path = _choose_web_search_path(user_message)
        try:
            research_agent = get_agent("research_agent")
        except KeyError:
            return ""

        _emit_progress(progress_callback, "Searching internet")
        record_trace_event(
            kind="research.web",
            message="building web research context",
            payload={"search_path": search_path, "query": query},
        )
        try:
            result = await asyncio.to_thread(
                research_agent.execute,
                "web_search",
                {
                    "query": query,
                    "num_results": 4,
                    "engine": search_path,
                    "search_path": search_path,
                },
            )
        except Exception as exc:
            logger.debug("Web research search failed: %s", exc)
            return ""

        if not result.success:
            return ""

        data = result.data or {}
        results = data.get("results") or []
        if not isinstance(results, list) or not results:
            return ""

        blocks = [
            "### Search Query",
            f"- Query: {query}",
            f"- Search engine: {data.get('search_engine', 'unknown')}",
            f"- Search path: {data.get('search_path', 'unknown')}",
            "",
            "### Top Results",
        ]
        for index, item in enumerate(results[:4], start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            citation = str(item.get("citation") or "").strip() or f"[W{index}]"
            quoted_evidence = str(item.get("quoted_evidence") or snippet).strip()
            if not title and not url and not snippet:
                continue
            line = f"- {citation} {title}" if title else f"- {citation} Result"
            if snippet:
                line += f": {snippet}"
            if quoted_evidence:
                line += f" | evidence: {quoted_evidence[:180]}"
            if url:
                line += f" ({url})"
            blocks.append(line)
        top_urls = [
            str(item.get("url") or "").strip()
            for item in results[:2]
            if isinstance(item, dict) and str(item.get("url") or "").strip()
        ]
        if top_urls and research_agent is not None:
            _emit_progress(progress_callback, "Fetching research pages")
            fetched_pages: list[dict[str, Any]] = []
            for url in top_urls:
                try:
                    fetch_result = await asyncio.to_thread(
                        research_agent.execute,
                        "fetch_url",
                        {"url": url, "extract_text": True},
                    )
                except Exception as exc:
                    logger.debug("Research fetch failed for %s: %s", url, exc)
                    continue
                if not fetch_result.success:
                    continue
                data = fetch_result.data or {}
                page_text = str(data.get("content") or "")
                summary_text = ""
                if page_text:
                    try:
                        summary_result = await asyncio.to_thread(
                            research_agent.execute,
                            "summarize",
                            {
                                "text": page_text[:6000],
                                "max_points": 4,
                                "style": "bullet",
                            },
                        )
                        if summary_result.success:
                            summary_text = str((summary_result.data or {}).get("summary") or "").strip()
                    except Exception as exc:
                        logger.debug("Research summary failed for %s: %s", url, exc)
                if not summary_text:
                    summary_text = page_text[:1200].strip()
                fetched_pages.append(
                    {
                        "url": url,
                        "summary": summary_text,
                        "excerpt": page_text[:300].strip(),
                        "quoted_evidence": str(data.get("quoted_evidence") or page_text[:220]).strip(),
                        "citation": str(data.get("citation") or f"[W{len(fetched_pages) + 1}]"),
                    }
                )

            if fetched_pages:
                blocks.append("")
                blocks.append("### Fetched Pages")
                for page in fetched_pages:
                    blocks.append(f"- {page['citation']} {page['url']}")
                    if page.get("summary"):
                        blocks.append(f"  - Summary: {page['summary']}")
                    if page.get("excerpt"):
                        blocks.append(f"  - Evidence excerpt: {page['excerpt']}")
                if page.get("quoted_evidence"):
                    blocks.append(f"  - Quoted evidence: {page['quoted_evidence']}")
        record_trace_event(
            kind="research.web",
            message="web research context built",
            payload={
                "search_path": data.get("search_path", "unknown"),
                "result_count": len(results),
                "fetched_pages": len(fetched_pages) if top_urls else 0,
            },
        )

        blocks.append("")
        blocks.append("### Guidance")
        blocks.append("- Use the search results and fetched pages above as the evidence base.")
        blocks.append("- Answer the topic directly and do not repeat Limbi's internal agent list.")
        blocks.append("- Cite claims using the source labels like [W1] or [U1] where possible.")
        blocks.append("- If the evidence conflicts, say so instead of forcing a confident answer.")
        return "\n".join(blocks).strip()

    async def _repair_research_answer(
        self,
        user_message: str,
        current_answer: str,
        *,
        url_research_context: str = "",
        web_research_context: str = "",
    ) -> str:
        research_blocks = [
            block
            for block in (url_research_context.strip(), web_research_context.strip())
            if block
        ]
        if not research_blocks:
            return ""

        try:
            repair_llm = self._ensure_llm(
                max_tokens=min(self._provider.config.max_tokens, 384),
                temperature=0.0,
            )
            research_text = "\n\n".join(research_blocks)
            repair_messages = [
                SystemMessage(
                    content=(
                        "You rewrite research answers. Use only the supplied research context. "
                        "Do not mention Limbi internals, the agent registry, shared memory, or "
                        "tool logs. Answer the user's topic directly and concisely. "
                        "Keep or add source citations like [U1] and [W1] when making claims."
                    )
                ),
                HumanMessage(
                    content=(
                        f"User question:\n{user_message}\n\n"
                        f"Research context:\n{research_text}\n\n"
                        f"Bad draft to replace:\n{current_answer}\n\n"
                        "Write the corrected final answer now."
                    )
                ),
            ]
            response = await asyncio.to_thread(repair_llm.invoke, repair_messages)
            repaired = str(getattr(response, "content", "") or "").strip()
            if repaired and not _looks_like_internal_agent_dump(repaired):
                return repaired
        except Exception as exc:
            logger.debug("Research answer repair failed: %s", exc)
        return ""

    async def chat(
        self,
        user_message: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:

        trace_id = start_trace(
            session_id=self._session_id,
            prompt=user_message,
            provider=self._provider.provider_name(),
            model=self._provider.config.model,
        )
        record_trace_event(
            kind="prompt.ingest",
            message="prompt received",
            payload={
                "session_id": self._session_id,
                "provider": self._provider.provider_name(),
                "model": self._provider.config.model,
                "prompt_length": len(user_message),
            },
        )

        clarification_questions = _needs_clarification(user_message)
        if clarification_questions:
            final_text = "\n".join(f"- {q}" for q in clarification_questions)
            finish_trace(status="clarification", final_answer=final_text)
            return {
                "conversation_text": final_text,
                "delegations_executed": [],
                "errors": [],
                "metrics": {
                    "latency_ms": 0.0,
                    "latency_s": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "task_route": "clarify",
                    "route_confidence": 0.35,
                    "route_reason": "request is ambiguous",
                    "trace_id": trace_id,
                    "estimated_hallucination_risk_percent": 5,
                    "estimated_confidence_percent": 95,
                },
                "needs_clarification": True,
            }

        if provider_requires_api_key(self._provider.provider_name()) and not self._provider.config.api_key:
            blocked_text = (
                f"Selected provider `{self._provider.provider_name()}` requires `LLM_API_KEY`.\n\n"
                "Set the key or switch to `ollama` for a local no-key setup."
            )
            finish_trace(status="blocked", final_answer=blocked_text)
            return {
                "conversation_text": blocked_text,
                "delegations_executed": [],
                "errors": ["Missing API key for selected provider"],
                "metrics": {
                    "latency_ms": 0.0,
                    "latency_s": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "task_route": "blocked",
                    "route_confidence": 0.0,
                    "route_reason": "provider requires an API key",
                    "trace_id": trace_id,
                    "estimated_hallucination_risk_percent": 8,
                    "estimated_confidence_percent": 92,
                },
                "requires_api_key": True,
            }

        self._sync_session_state()
        _emit_progress(progress_callback, "Planning task")
        self._record_turn(
            "user",
            user_message,
            metadata={
                "provider": self._provider.provider_name(),
                "model": self._provider.config.model,
            },
        )

        task_route_info = _decide_task_route(user_message)
        task_route = task_route_info["route"]
        route_confidence = float(task_route_info.get("confidence", 0.0) or 0.0)
        _emit_progress(progress_callback, f"Routing: {task_route}")
        record_trace_event(
            kind="routing.decision",
            message=f"route={task_route}",
            payload={
                "route": task_route,
                "reason": task_route_info.get("reason", ""),
                "confidence": route_confidence,
            },
        )

        research_mode = task_route == "research" or _looks_like_web_research_prompt(user_message)
        search_path = _choose_web_search_path(user_message) if research_mode else ""
        rag_context = self._vector_store.get_context_string(user_message)
        if research_mode:
            rag_context = ""
        if rag_context:
            _emit_progress(progress_callback, "Gathering workspace context")
            record_trace_event(
                kind="context.workspace",
                message="workspace context loaded",
                payload={"chars": len(rag_context)},
            )
        url_research_context = await self._build_url_research_context(
            user_message,
            progress_callback=progress_callback,
        )
        web_research_context = await self._build_web_research_context(
            user_message,
            progress_callback=progress_callback,
        )
        if url_research_context or web_research_context:
            record_trace_event(
                kind="research.context",
                message="research context prepared",
                payload={
                    "url_context_chars": len(url_research_context),
                    "web_context_chars": len(web_research_context),
                    "search_path": search_path,
                },
            )
        _emit_progress(progress_callback, "Calculating runtime budget")
        agent_registry = _build_agent_registry_text()
        recent_execs = "" if research_mode else _build_recent_executions_text()
        shared_ctx = get_session_context(
            self._session_id,
            query=user_message,
            include_state=not research_mode,
        )
        task_profile = _estimate_task_complexity(
            user_message,
            rag_context=rag_context,
            url_research_context=url_research_context,
            web_research_context=web_research_context,
            shared_context=shared_ctx,
        )
        research_source_count = url_research_context.count("### Source ") + web_research_context.count("- [W")
        suggested_model = _suggest_model_for_task(
            self._provider.provider_name(),
            task_route,
            task_profile["level"],
            self._provider.config.model,
        )
        runtime_model = suggested_model or self._provider.config.model
        if suggested_model and suggested_model != self._provider.config.model:
            _emit_progress(progress_callback, f"Routing model: {suggested_model}")
        try:
            self._current_goal = user_message[:1200]
            self._current_route = task_route
            self._route_reason = str(task_route_info.get("reason", ""))
            self._route_confidence = route_confidence
            self._recommended_model = runtime_model
            self._search_path = search_path
            set_shared_state_value(self._session_id, "current_route", task_route)
            set_shared_state_value(self._session_id, "route_reason", task_route_info.get("reason", ""))
            set_shared_state_value(self._session_id, "route_confidence", route_confidence)
            set_shared_state_value(self._session_id, "recommended_model", runtime_model)
            set_shared_state_value(self._session_id, "current_goal", self._current_goal)
            set_shared_state_value(self._session_id, "search_path", self._search_path)
        except Exception:
            pass
        runtime_limits = _suggest_runtime_limits(
            task_profile["level"],
            self._provider.config.max_tokens,
            self._provider.config.temperature,
        )
        llm = self._ensure_llm(
            max_tokens=runtime_limits["max_tokens"],
            temperature=runtime_limits["temperature"],
            model_name=runtime_model,
        )
        system_text = SYSTEM_PROMPT.format(
            agent_registry=agent_registry,
            rag_context=rag_context,
            url_research_context=url_research_context,
            web_research_context=web_research_context,
            recent_executions=recent_execs,
            shared_agent_context=shared_ctx,
        )

        messages = [SystemMessage(content=system_text)]
        if self._conversation_summary:
            messages.append(SystemMessage(
                content=f"[CONVERSATION SUMMARY OF EARLIER MESSAGES]\n{self._conversation_summary}"
            ))
        messages.extend(_dedupe_history_messages(self._history, limit=8))
        messages.append(HumanMessage(content=user_message))

        started = time.perf_counter()
        try:
            _emit_progress(progress_callback, "Generating response")
            response = await asyncio.to_thread(llm.invoke, messages)
            raw_text: str = response.content
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            finish_trace(status="error", final_answer="LLM provider unavailable")
            return {
                "conversation_text": (
                    f" I couldn't reach the local model (`{self._model_name}`).\n\n"
                    f"Make sure Ollama is running: `ollama serve`"
                ),
                "delegations_executed": [],
                "errors": ["LLM provider unavailable"],
                "metrics": {
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                    "latency_s": round(time.perf_counter() - started, 2),
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "trace_id": trace_id,
                    "estimated_hallucination_risk_percent": 95,
                    "estimated_confidence_percent": 5,
                },
            }

        parsed: ParsedOutput = parse_llm_output(raw_text)

        delegation_results: list[dict[str, Any]] = []
        if parsed.has_delegations:
            selected_agents = sorted(
                {
                    str(payload.get("agent", "")).strip()
                    for payload in parsed.delegation_payloads
                    if str(payload.get("agent", "")).strip()
                }
            )
            if selected_agents:
                _emit_progress(progress_callback, f"Selected agents: {', '.join(selected_agents)}")
            _emit_progress(progress_callback, "Running delegated agents")
            delegation_results = await self._execute_delegations_parallel(
                parsed.delegation_payloads,
                progress_callback=progress_callback,
            )
            record_trace_event(
                kind="delegation.summary",
                message="delegated work completed",
                payload={"count": len(delegation_results)},
            )

            result_summary = "\n".join(
                f"- **{r['agent']}.{r['action']}**: {'' if r['success'] else ''} "
                f"{r.get('data', {}).get('message', r.get('error', ''))}"
                for r in delegation_results
            )
            feedback_msg = f"\n\n---\n** Agent Execution Results:**\n{result_summary}"
            parsed.conversation_text += feedback_msg

        if delegation_results and _looks_like_delegation_only(parsed.conversation_text):
            synthesized = _summarize_delegation_results(delegation_results, user_message)
            parsed.conversation_text = (
                f"{parsed.conversation_text}\n\n**Final Answer**\n{synthesized}"
            ).strip()
        if research_mode and _looks_like_internal_agent_dump(parsed.conversation_text):
            _emit_progress(progress_callback, "Rewriting research answer")
            repaired = await self._repair_research_answer(
                user_message,
                parsed.conversation_text,
                url_research_context=url_research_context,
                web_research_context=web_research_context,
            )
            if repaired:
                parsed.conversation_text = repaired
        _emit_progress(progress_callback, "Finalizing response")

        self._record_turn(
            "assistant",
            parsed.conversation_text,
            metadata={
                "task_level": task_profile["level"],
                "task_score": task_profile["score"],
                "provider": self._provider.provider_name(),
                "model": runtime_model,
                "max_tokens": runtime_limits["max_tokens"],
            },
        )

        self._history.append(HumanMessage(content=user_message))
        self._history.append(AIMessage(content=raw_text))
        await self._manage_history()
        self._sync_session_state()

        elapsed_ms = (time.perf_counter() - started) * 1000
        metrics = build_runtime_metrics(
            response=response,
            prompt_text=user_message,
            raw_text=raw_text,
            parsed_errors=parsed.parse_errors,
            delegations=delegation_results,
            elapsed_ms=elapsed_ms,
            clarification_requested=False,
            task_complexity=task_profile["level"],
            token_budget=runtime_limits["max_tokens"],
            memory_turns=len(self._history),
            task_route=task_route,
            route_confidence=route_confidence,
            route_reason=str(task_route_info.get("reason", "")),
            search_path=search_path,
            research_source_count=research_source_count,
            recommended_model=runtime_model,
            effective_model=runtime_model,
            trace_id=trace_id,
        )
        finish_trace(
            status="completed",
            final_answer=parsed.conversation_text,
            prompt_tokens=metrics.get("prompt_tokens", 0),
            completion_tokens=metrics.get("completion_tokens", 0),
            total_tokens=metrics.get("total_tokens", 0),
            search_path=search_path,
            research_source_count=research_source_count,
        )

        return {
            "conversation_text": parsed.conversation_text,
            "delegations_executed": delegation_results,
            "errors": parsed.parse_errors,
            "metrics": metrics,
        }

    async def chat_stream(
        self,
        user_message: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:

        trace_id = start_trace(
            session_id=self._session_id,
            prompt=user_message,
            provider=self._provider.provider_name(),
            model=self._provider.config.model,
        )
        record_trace_event(
            kind="prompt.ingest",
            message="prompt received",
            payload={
                "session_id": self._session_id,
                "provider": self._provider.provider_name(),
                "model": self._provider.config.model,
                "prompt_length": len(user_message),
            },
        )

        clarification_questions = _needs_clarification(user_message)
        if clarification_questions:
            final_text = "\n".join(f"- {q}" for q in clarification_questions)
            finish_trace(status="clarification", final_answer=final_text)
            yield {
                "type": "done",
                "conversation_text": final_text,
                "delegations": [],
                "errors": [],
                "metrics": {
                    "latency_ms": 0.0,
                    "latency_s": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "task_route": "clarify",
                    "route_confidence": 0.35,
                    "route_reason": "request is ambiguous",
                    "trace_id": trace_id,
                    "estimated_hallucination_risk_percent": 5,
                    "estimated_confidence_percent": 95,
                },
                "needs_clarification": True,
            }
            return

        if provider_requires_api_key(self._provider.provider_name()) and not self._provider.config.api_key:
            blocked_text = (
                f"Selected provider `{self._provider.provider_name()}` requires `LLM_API_KEY`."
            )
            finish_trace(status="blocked", final_answer=blocked_text)
            yield {
                "type": "error",
                "content": blocked_text,
            }
            yield {
                "type": "done",
                "conversation_text": "",
                "delegations": [],
                "errors": ["Missing API key for selected provider"],
                "metrics": {
                    "latency_ms": 0.0,
                    "latency_s": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "task_route": "blocked",
                    "route_confidence": 0.0,
                    "route_reason": "provider requires an API key",
                    "trace_id": trace_id,
                    "estimated_hallucination_risk_percent": 8,
                    "estimated_confidence_percent": 92,
                },
                "requires_api_key": True,
            }
            return

        self._sync_session_state()
        _emit_progress(progress_callback, "Planning task")
        self._record_turn(
            "user",
            user_message,
            metadata={
                "provider": self._provider.provider_name(),
                "model": self._provider.config.model,
            },
        )

        task_route_info = _decide_task_route(user_message)
        task_route = task_route_info["route"]
        route_confidence = float(task_route_info.get("confidence", 0.0) or 0.0)
        _emit_progress(progress_callback, f"Routing: {task_route}")
        record_trace_event(
            kind="routing.decision",
            message=f"route={task_route}",
            payload={
                "route": task_route,
                "reason": task_route_info.get("reason", ""),
                "confidence": route_confidence,
            },
        )

        research_mode = task_route == "research" or _looks_like_web_research_prompt(user_message)
        search_path = _choose_web_search_path(user_message) if research_mode else ""
        rag_context = self._vector_store.get_context_string(user_message)
        if research_mode:
            rag_context = ""
        if rag_context:
            _emit_progress(progress_callback, "Gathering workspace context")
            record_trace_event(
                kind="context.workspace",
                message="workspace context loaded",
                payload={"chars": len(rag_context)},
            )
        url_research_context = await self._build_url_research_context(
            user_message,
            progress_callback=progress_callback,
        )
        web_research_context = await self._build_web_research_context(
            user_message,
            progress_callback=progress_callback,
        )
        if url_research_context or web_research_context:
            record_trace_event(
                kind="research.context",
                message="research context prepared",
                payload={
                    "url_context_chars": len(url_research_context),
                    "web_context_chars": len(web_research_context),
                    "search_path": search_path,
                },
            )
        _emit_progress(progress_callback, "Calculating runtime budget")
        agent_registry = _build_agent_registry_text()
        recent_execs = "" if research_mode else _build_recent_executions_text()
        shared_ctx = get_session_context(
            self._session_id,
            query=user_message,
            include_state=not research_mode,
        )
        task_profile = _estimate_task_complexity(
            user_message,
            rag_context=rag_context,
            url_research_context=url_research_context,
            web_research_context=web_research_context,
            shared_context=shared_ctx,
        )
        research_source_count = url_research_context.count("### Source ") + web_research_context.count("- [W")
        suggested_model = _suggest_model_for_task(
            self._provider.provider_name(),
            task_route,
            task_profile["level"],
            self._provider.config.model,
        )
        runtime_model = suggested_model or self._provider.config.model
        if suggested_model and suggested_model != self._provider.config.model:
            _emit_progress(progress_callback, f"Routing model: {suggested_model}")
        try:
            self._current_goal = user_message[:1200]
            self._current_route = task_route
            self._route_reason = str(task_route_info.get("reason", ""))
            self._route_confidence = route_confidence
            self._recommended_model = runtime_model
            self._search_path = search_path
            set_shared_state_value(self._session_id, "current_route", task_route)
            set_shared_state_value(self._session_id, "route_reason", task_route_info.get("reason", ""))
            set_shared_state_value(self._session_id, "route_confidence", route_confidence)
            set_shared_state_value(self._session_id, "recommended_model", runtime_model)
            set_shared_state_value(self._session_id, "current_goal", self._current_goal)
            set_shared_state_value(self._session_id, "search_path", self._search_path)
        except Exception:
            pass
        runtime_limits = _suggest_runtime_limits(
            task_profile["level"],
            self._provider.config.max_tokens,
            self._provider.config.temperature,
        )
        llm = self._ensure_llm(
            max_tokens=runtime_limits["max_tokens"],
            temperature=runtime_limits["temperature"],
            model_name=runtime_model,
        )
        system_text = SYSTEM_PROMPT.format(
            agent_registry=agent_registry,
            rag_context=rag_context,
            url_research_context=url_research_context,
            web_research_context=web_research_context,
            recent_executions=recent_execs,
            shared_agent_context=shared_ctx,
        )

        messages = [SystemMessage(content=system_text)]
        if self._conversation_summary:
            messages.append(SystemMessage(
                content=f"[CONVERSATION SUMMARY]\n{self._conversation_summary}"
            ))
        messages.extend(_dedupe_history_messages(self._history, limit=8))
        messages.append(HumanMessage(content=user_message))

        full_text = ""
        started = time.perf_counter()
        try:
            _emit_progress(progress_callback, "Generating response")
            async for chunk in llm.astream(messages):
                token = chunk.content
                if token:
                    full_text += token
                    yield {"type": "token", "content": token}
        except Exception as exc:
            finish_trace(status="error", final_answer="LLM provider unavailable")
            yield {
                "type": "error",
                "content": "LLM error: provider unavailable. Make sure Ollama is running.",
            }
            return

        parsed = parse_llm_output(full_text)

        delegation_results: list[dict[str, Any]] = []
        if parsed.has_delegations:
            yield {"type": "delegation_start", "count": len(parsed.delegation_payloads)}
            selected_agents = sorted(
                {
                    str(payload.get("agent", "")).strip()
                    for payload in parsed.delegation_payloads
                    if str(payload.get("agent", "")).strip()
                }
            )
            if selected_agents:
                _emit_progress(progress_callback, f"Selected agents: {', '.join(selected_agents)}")
            _emit_progress(progress_callback, "Running delegated agents")
            delegation_results = await self._execute_delegations_parallel(
                parsed.delegation_payloads,
                progress_callback=progress_callback,
            )
            record_trace_event(
                kind="delegation.summary",
                message="delegated work completed",
                payload={"count": len(delegation_results)},
            )
            for result in delegation_results:
                yield {"type": "delegation_result", "result": result}

        if delegation_results and _looks_like_delegation_only(parsed.conversation_text):
            synthesized = _summarize_delegation_results(delegation_results, user_message)
            parsed.conversation_text = (
                f"{parsed.conversation_text}\n\n**Final Answer**\n{synthesized}"
            ).strip()
        if research_mode and _looks_like_internal_agent_dump(parsed.conversation_text):
            _emit_progress(progress_callback, "Rewriting research answer")
            repaired = await self._repair_research_answer(
                user_message,
                parsed.conversation_text,
                url_research_context=url_research_context,
                web_research_context=web_research_context,
            )
            if repaired:
                parsed.conversation_text = repaired
        _emit_progress(progress_callback, "Finalizing response")

        self._record_turn(
            "assistant",
            parsed.conversation_text,
            metadata={
                "task_level": task_profile["level"],
                "task_score": task_profile["score"],
                "provider": self._provider.provider_name(),
                "model": runtime_model,
                "max_tokens": runtime_limits["max_tokens"],
            },
        )

        self._history.append(HumanMessage(content=user_message))
        self._history.append(AIMessage(content=full_text))
        await self._manage_history()
        self._sync_session_state()

        metrics = build_runtime_metrics(
            response=None,
            prompt_text=user_message,
            raw_text=full_text,
            parsed_errors=parsed.parse_errors,
            delegations=delegation_results,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            clarification_requested=False,
            task_complexity=task_profile["level"],
            token_budget=runtime_limits["max_tokens"],
            memory_turns=len(self._history),
            task_route=task_route,
            route_confidence=route_confidence,
            route_reason=str(task_route_info.get("reason", "")),
            search_path=search_path,
            research_source_count=research_source_count,
            recommended_model=runtime_model,
            effective_model=runtime_model,
            trace_id=trace_id,
        )
        finish_trace(
            status="completed",
            final_answer=parsed.conversation_text,
            prompt_tokens=metrics.get("prompt_tokens", 0),
            completion_tokens=metrics.get("completion_tokens", 0),
            total_tokens=metrics.get("total_tokens", 0),
            search_path=search_path,
            research_source_count=research_source_count,
        )

        yield {
            "type": "done",
            "conversation_text": parsed.conversation_text,
            "delegations": delegation_results,
            "errors": parsed.parse_errors,
            "metrics": metrics,
        }

    async def _execute_delegations_parallel(
        self,
        delegations: list[dict[str, Any]],
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[dict[str, Any]]:

        tasks = [
            self._execute_with_retry(d, progress_callback=progress_callback) for d in delegations
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final: list[dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                agent_name = delegations[i].get("agent", "unknown")
                action = delegations[i].get("action", "unknown")
                error_result = AgentResult(
                    success=False,
                    agent=agent_name,
                    action=action,
                    error="Delegation execution failed",
                )
                final.append(error_result.to_dict())
            else:
                final.append(result.to_dict())
        return final

    async def _execute_with_retry(
        self,
        delegation: dict[str, Any],
        max_retries: int = MAX_RETRIES,
        progress_callback: Callable[[str], None] | None = None,
    ) -> AgentResult:

        agent_name = delegation.get("agent", "")
        action = delegation.get("action", "")
        params = delegation.get("params", {})

        last_error: str | None = None
        for attempt in range(max_retries):
            start_time = time.time()
            try:
                policy = load_config()
                decision = evaluate_permission(policy, "agent_scopes", agent_name, action)
                record_trace_event(
                    kind="agent.permission",
                    agent=agent_name,
                    action=action,
                    message="permission evaluated",
                    status="info",
                    payload={
                        "allowed": decision.allowed,
                        "reason": decision.reason,
                        "attempt": attempt + 1,
                    },
                )
                if not decision.allowed:
                    record_trace_event(
                        kind="agent.execute",
                        agent=agent_name,
                        action=action,
                        message="permission denied",
                        status="error",
                        payload={"reason": decision.reason, "attempt": attempt + 1},
                    )
                    return AgentResult(
                        success=False,
                        agent=agent_name,
                        action=action,
                        error=decision.reason or f"Agent scope blocked for {agent_name}",
                    )
                agent = get_agent(agent_name)
                _emit_progress(progress_callback, f"Running {agent_name}.{action}")
                result = await asyncio.to_thread(agent.execute, action, params)
                duration = (time.time() - start_time) * 1000

                log_execution(
                    agent=agent_name,
                    action=action,
                    params=params,
                    success=result.success,
                    result_data=result.data,
                    error=result.error,
                    duration_ms=duration,
                )
                record_trace_event(
                    kind="agent.execute",
                    agent=agent_name,
                    action=action,
                    message="agent completed",
                    status="success" if result.success else "error",
                    payload={
                        "success": result.success,
                        "duration_ms": duration,
                        "error": result.error,
                    },
                )

                # ── Auto-publish result to the shared context memory bus ──
                try:
                    publish_agent_result(
                        source_agent=agent_name,
                        action=action,
                        result_data=result.data or {},
                        success=result.success,
                        session_id=self._session_id,
                    )
                except Exception as pub_err:
                    logger.debug("Context publish failed (non-fatal): %s", pub_err)

                if result.success:
                    _emit_progress(progress_callback, f"Collected result from {agent_name}.{action}")
                    if attempt > 0:
                        logger.info(
                            "%s.%s succeeded on attempt %d", agent_name, action, attempt + 1
                        )
                    return result

                if "Unknown action" in (result.error or ""):
                    return result

                last_error = result.error
                logger.warning(
                    "%s.%s failed (attempt %d/%d): %s",
                    agent_name, action, attempt + 1, max_retries, result.error,
                )

            except KeyError as exc:

                duration = (time.time() - start_time) * 1000
                record_trace_event(
                    kind="agent.execute",
                    agent=agent_name,
                    action=action,
                    message="agent not found",
                    status="error",
                    payload={"duration_ms": duration},
                )
                log_execution(
                    agent=agent_name, action=action, params=params,
                    success=False, error="Agent not found", duration_ms=duration,
                )
                return AgentResult(
                    success=False, agent=agent_name, action=action, error="Agent not found"
                )
            except Exception as exc:
                duration = (time.time() - start_time) * 1000
                last_error = "Agent execution failed"
                record_trace_event(
                    kind="agent.execute",
                    agent=agent_name,
                    action=action,
                    message="agent exception",
                    status="error",
                    payload={"duration_ms": duration, "error": last_error},
                )
                log_execution(
                    agent=agent_name, action=action, params=params,
                    success=False, error=last_error, duration_ms=duration,
                )
                logger.warning(
                    "%s.%s exception (attempt %d/%d): %s",
                    agent_name, action, attempt + 1, max_retries, last_error,
                )

            if attempt < max_retries - 1:
                wait = RETRY_BACKOFF_BASE * (2 ** attempt)
                await asyncio.sleep(wait)

        return AgentResult(
            success=False,
            agent=agent_name,
            action=action,
            error=f"Failed after {max_retries} retries. Last error: {last_error}",
        )

    async def _manage_history(self) -> None:

        if len(self._history) < SUMMARIZE_THRESHOLD:
            return

        to_summarize = self._history[:-6]
        to_keep = self._history[-6:]

        summary_prompt = (
            "Summarize the following conversation in 3-5 bullet points. "
            "Focus on key topics discussed, decisions made, and actions taken:\n\n"
        )
        for msg in to_summarize:
            role = "User" if isinstance(msg, HumanMessage) else "AI"

            content = msg.content[:500] + ("..." if len(msg.content) > 500 else "")
            summary_prompt += f"**{role}:** {content}\n\n"

        try:
            llm = self._ensure_llm()
            response = await asyncio.to_thread(
                llm.invoke,
                [SystemMessage(content="You are a concise summarizer. Output only bullet points."),
                 HumanMessage(content=summary_prompt)],
            )
            new_summary = response.content.strip()

            if self._conversation_summary:
                self._conversation_summary = _compact_summary(self._conversation_summary, new_summary, limit=1200)
            else:
                self._conversation_summary = _compact_summary("", new_summary, limit=1200)

            try:
                set_shared_state_value(self._session_id, "conversation_summary", self._conversation_summary)
            except Exception as exc:
                logger.debug("Failed to persist conversation summary: %s", exc)

            self._history = to_keep
            logger.info(
                "Summarized %d messages into %d chars, keeping %d recent",
                len(to_summarize), len(self._conversation_summary), len(to_keep),
            )
        except Exception as exc:

            logger.warning("Summarization failed (%s), falling back to truncation", exc)
            self._history = self._history[-MAX_HISTORY_MESSAGES:]

    def clear_history(self) -> None:

        self._history.clear()
        self._conversation_summary = ""
        self._current_goal = ""
        self._current_route = "direct"
        self._route_reason = ""
        self._route_confidence = 0.0
        self._recommended_model = ""
        self._search_path = ""
        try:
            set_shared_state_value(self._session_id, "conversation_summary", "")
            set_shared_state_value(self._session_id, "current_goal", "")
            set_shared_state_value(self._session_id, "current_route", "")
            set_shared_state_value(self._session_id, "route_reason", "")
            set_shared_state_value(self._session_id, "route_confidence", 0.0)
            set_shared_state_value(self._session_id, "recommended_model", "")
            set_shared_state_value(self._session_id, "search_path", "")
            set_shared_state_value(self._session_id, "current_focus", "")
            set_shared_state_value(self._session_id, "last_role", "")
            set_shared_state_value(self._session_id, "last_response_summary", "")
            set_shared_state_value(self._session_id, "turn_count", 0)
        except Exception as exc:
            logger.debug("Failed to reset shared session state: %s", exc)
        logger.info("Conversation history cleared")

    def get_agent_info(self) -> dict[str, list[str]]:

        return list_agents()

    def ingest_codebase(self, directory: str) -> dict[str, Any]:

        return self._vector_store.ingest_directory(directory)

    def vector_store_stats(self) -> dict[str, Any]:

        return self._vector_store.stats()
