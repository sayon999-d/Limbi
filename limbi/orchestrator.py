

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, AsyncIterator

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from .llm_provider import get_llm_provider, ProviderConfig, provider_requires_api_key

from .payload_parser import ParsedOutput, parse_llm_output
from .agents import get_agent, list_agents, AgentResult
from .vector_store import VectorStore
from .audit_log import log_execution, get_recent_executions
from .agents.context_memory_agent import publish_agent_result, get_session_context
from .runtime_metrics import build_runtime_metrics

logger = logging.getLogger("limbi.orchestrator")

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 0.5

MAX_HISTORY_MESSAGES = 40
SUMMARIZE_THRESHOLD = 30

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
- If a requested capability is not registered, say so plainly and suggest the closest existing agent.
- When listing required or optional agents, keep the list limited to real registered agents only.

## Clarification Rules
- If the request is underspecified, ask up to 3 short clarifying questions before acting.
- If file paths, output targets, runtime targets, or provider details are missing, ask before guessing.
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
"""


def _needs_clarification(user_message: str) -> list[str]:
    text = user_message.lower().strip()
    words = text.split()

    task_verbs = {"build", "create", "make", "design", "write", "implement", "fix", "improve", "optimize", "generate"}
    project_words = {"app", "project", "tool", "site", "api", "workflow", "agent"}
    stack_words = {"python", "javascript", "typescript", "react", "next", "fastapi", "flask", "vue", "svelte", "cli", "desktop", "mobile"}

    if any(verb in text for verb in task_verbs) and len(words) <= 14:
        questions = [
            "What stack or language do you want me to use?",
            "Where should I save the output inside the workspace?",
        ]
        if not any(word in text for word in stack_words):
            return questions

    if any(word in text for word in project_words) and not any(word in text for word in stack_words):
        return [
            "Which stack should I target?",
            "Should I create files in the current workspace root or in a subfolder?",
        ]

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
        recent = get_recent_executions(limit=5)
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

        self._vector_store = VectorStore()

        self._llm: BaseChatModel | None = None

        self._session_id = session_id

        logger.info(
            "Orchestrator init - provider=%s model=%s session=%s",
            self._provider.provider_name(),
            self._model_name,
            self._session_id,
        )

    def _ensure_llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = self._provider.get_chat_model()
        return self._llm

    async def chat(self, user_message: str) -> dict[str, Any]:

        clarification_questions = _needs_clarification(user_message)
        if clarification_questions:
            return {
                "conversation_text": "\n".join(f"- {q}" for q in clarification_questions),
                "delegations_executed": [],
                "errors": [],
                "metrics": {
                    "latency_ms": 0.0,
                    "latency_s": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_hallucination_risk_percent": 5,
                    "estimated_confidence_percent": 95,
                },
                "needs_clarification": True,
            }

        if provider_requires_api_key(self._provider.provider_name()) and not self._provider.config.api_key:
            return {
                "conversation_text": (
                    f"Selected provider `{self._provider.provider_name()}` requires `LLM_API_KEY`.\n\n"
                    "Set the key or switch to `ollama` for a local no-key setup."
                ),
                "delegations_executed": [],
                "errors": ["Missing API key for selected provider"],
                "metrics": {
                    "latency_ms": 0.0,
                    "latency_s": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_hallucination_risk_percent": 8,
                    "estimated_confidence_percent": 92,
                },
                "requires_api_key": True,
            }

        llm = self._ensure_llm()

        rag_context = self._vector_store.get_context_string(user_message)

        agent_registry = _build_agent_registry_text()
        recent_execs = _build_recent_executions_text()
        shared_ctx = get_session_context(self._session_id)
        system_text = SYSTEM_PROMPT.format(
            agent_registry=agent_registry,
            rag_context=rag_context,
            recent_executions=recent_execs,
            shared_agent_context=shared_ctx,
        )

        messages = [SystemMessage(content=system_text)]
        if self._conversation_summary:
            messages.append(SystemMessage(
                content=f"[CONVERSATION SUMMARY OF EARLIER MESSAGES]\n{self._conversation_summary}"
            ))
        messages.extend(self._history)
        messages.append(HumanMessage(content=user_message))

        started = time.perf_counter()
        try:
            response = await asyncio.to_thread(llm.invoke, messages)
            raw_text: str = response.content
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
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
                    "estimated_hallucination_risk_percent": 95,
                    "estimated_confidence_percent": 5,
                },
            }

        parsed: ParsedOutput = parse_llm_output(raw_text)

        delegation_results: list[dict[str, Any]] = []
        if parsed.has_delegations:
            delegation_results = await self._execute_delegations_parallel(
                parsed.delegation_payloads
            )

            result_summary = "\n".join(
                f"- **{r['agent']}.{r['action']}**: {'' if r['success'] else ''} "
                f"{r.get('data', {}).get('message', r.get('error', ''))}"
                for r in delegation_results
            )
            feedback_msg = f"\n\n---\n** Agent Execution Results:**\n{result_summary}"
            parsed.conversation_text += feedback_msg

        self._history.append(HumanMessage(content=user_message))
        self._history.append(AIMessage(content=raw_text))
        await self._manage_history()

        elapsed_ms = (time.perf_counter() - started) * 1000
        metrics = build_runtime_metrics(
            response=response,
            prompt_text=user_message,
            raw_text=raw_text,
            parsed_errors=parsed.parse_errors,
            delegations=delegation_results,
            elapsed_ms=elapsed_ms,
            clarification_requested=False,
        )

        return {
            "conversation_text": parsed.conversation_text,
            "delegations_executed": delegation_results,
            "errors": parsed.parse_errors,
            "metrics": metrics,
        }

    async def chat_stream(self, user_message: str) -> AsyncIterator[dict[str, Any]]:

        clarification_questions = _needs_clarification(user_message)
        if clarification_questions:
            yield {
                "type": "done",
                "conversation_text": "\n".join(f"- {q}" for q in clarification_questions),
                "delegations": [],
                "errors": [],
                "metrics": {
                    "latency_ms": 0.0,
                    "latency_s": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_hallucination_risk_percent": 5,
                    "estimated_confidence_percent": 95,
                },
                "needs_clarification": True,
            }
            return

        if provider_requires_api_key(self._provider.provider_name()) and not self._provider.config.api_key:
            yield {
                "type": "error",
                "content": (
                    f"Selected provider `{self._provider.provider_name()}` requires `LLM_API_KEY`."
                ),
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
                    "estimated_hallucination_risk_percent": 8,
                    "estimated_confidence_percent": 92,
                },
                "requires_api_key": True,
            }
            return

        llm = self._ensure_llm()

        rag_context = self._vector_store.get_context_string(user_message)
        agent_registry = _build_agent_registry_text()
        recent_execs = _build_recent_executions_text()
        shared_ctx = get_session_context(self._session_id)
        system_text = SYSTEM_PROMPT.format(
            agent_registry=agent_registry,
            rag_context=rag_context,
            recent_executions=recent_execs,
            shared_agent_context=shared_ctx,
        )

        messages = [SystemMessage(content=system_text)]
        if self._conversation_summary:
            messages.append(SystemMessage(
                content=f"[CONVERSATION SUMMARY]\n{self._conversation_summary}"
            ))
        messages.extend(self._history)
        messages.append(HumanMessage(content=user_message))

        full_text = ""
        started = time.perf_counter()
        try:
            async for chunk in llm.astream(messages):
                token = chunk.content
                if token:
                    full_text += token
                    yield {"type": "token", "content": token}
        except Exception as exc:
            yield {
                "type": "error",
                "content": "LLM error: provider unavailable. Make sure Ollama is running.",
            }
            return

        parsed = parse_llm_output(full_text)

        delegation_results: list[dict[str, Any]] = []
        if parsed.has_delegations:
            yield {"type": "delegation_start", "count": len(parsed.delegation_payloads)}
            delegation_results = await self._execute_delegations_parallel(
                parsed.delegation_payloads
            )
            for result in delegation_results:
                yield {"type": "delegation_result", "result": result}

        self._history.append(HumanMessage(content=user_message))
        self._history.append(AIMessage(content=full_text))
        await self._manage_history()

        metrics = build_runtime_metrics(
            response=None,
            prompt_text=user_message,
            raw_text=full_text,
            parsed_errors=parsed.parse_errors,
            delegations=delegation_results,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            clarification_requested=False,
        )

        yield {
            "type": "done",
            "conversation_text": parsed.conversation_text,
            "delegations": delegation_results,
            "errors": parsed.parse_errors,
            "metrics": metrics,
        }

    async def _execute_delegations_parallel(
        self, delegations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:

        tasks = [
            self._execute_with_retry(d) for d in delegations
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
    ) -> AgentResult:

        agent_name = delegation.get("agent", "")
        action = delegation.get("action", "")
        params = delegation.get("params", {})

        last_error: str | None = None
        for attempt in range(max_retries):
            start_time = time.time()
            try:
                agent = get_agent(agent_name)
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

        to_summarize = self._history[:-10]
        to_keep = self._history[-10:]

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
                self._conversation_summary = (
                    f"{self._conversation_summary}\n\n"
                    f"[More recent context]\n{new_summary}"
                )

                if len(self._conversation_summary) > 2000:
                    self._conversation_summary = self._conversation_summary[-2000:]
            else:
                self._conversation_summary = new_summary

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
        logger.info("Conversation history cleared")

    def get_agent_info(self) -> dict[str, list[str]]:

        return list_agents()

    def ingest_codebase(self, directory: str) -> dict[str, Any]:

        return self._vector_store.ingest_directory(directory)

    def vector_store_stats(self) -> dict[str, Any]:

        return self._vector_store.stats()
