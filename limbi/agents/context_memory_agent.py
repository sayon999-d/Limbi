"""Context Memory Agent — Shared memory bus for inter-agent coordination.

Unlike the MemoryAgent (which stores personal/conversation memory), this agent
provides a **shared context layer** that allows agents to:
  • Publish findings, results, and context for other agents to consume
  • Subscribe to context from specific agents or tags
  • Build cumulative awareness across a multi-step delegation chain
  • Maintain a "working memory" for the current task so that later
    agents in a pipeline see what earlier agents discovered

Architecture:
    ┌──────────┐     store      ┌──────────────────┐     recall      ┌──────────┐
    │ Agent A  │ ──────────────►│  Context Memory  │◄─────────────── │ Agent B  │
    │(security)│                │      Bus         │                 │ (devops) │
    └──────────┘                └──────────────────┘                 └──────────┘
         │        broadcast           │                      │
         └───────────────────►  tags: [security]  ◄──────────┘
                                 scoped by session
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from typing import Any

from . import BaseAgent

logger = logging.getLogger("limbi.agents.context_memory")

_CTX_DB_PATH = os.getenv("CONTEXT_MEMORY_DB_PATH", "./limbi_context_memory.db")
_lock = threading.Lock()

# ── In-memory hot cache for the current session (fast reads) ──────────────
_hot_cache: dict[str, list[dict[str, Any]]] = {}   # session_id → entries
_agent_subscriptions: dict[str, set[str]] = {}       # agent_name → tag set


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_CTX_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_context_db() -> None:
    with _lock:
        conn = _get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS context_entries (
                id              TEXT PRIMARY KEY,
                session_id      TEXT NOT NULL DEFAULT 'global',
                source_agent    TEXT NOT NULL,
                target_agents   TEXT DEFAULT '["*"]',
                entry_type      TEXT NOT NULL DEFAULT 'context',
                content         TEXT NOT NULL,
                tags            TEXT DEFAULT '[]',
                priority        TEXT DEFAULT 'normal',
                metadata        TEXT DEFAULT '{}',
                created_at      TEXT NOT NULL,
                expires_at      TEXT,
                accessed_count  INTEGER DEFAULT 0,
                last_accessed   TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_handoffs (
                id              TEXT PRIMARY KEY,
                session_id      TEXT NOT NULL DEFAULT 'global',
                from_agent      TEXT NOT NULL,
                to_agent        TEXT NOT NULL,
                action_taken    TEXT NOT NULL,
                result_summary  TEXT NOT NULL,
                full_result     TEXT DEFAULT '{}',
                created_at      TEXT NOT NULL,
                consumed        INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS session_state (
                session_id      TEXT NOT NULL,
                key             TEXT NOT NULL,
                value           TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                PRIMARY KEY (session_id, key)
            );

            CREATE INDEX IF NOT EXISTS idx_ctx_session ON context_entries(session_id);
            CREATE INDEX IF NOT EXISTS idx_ctx_source ON context_entries(source_agent);
            CREATE INDEX IF NOT EXISTS idx_ctx_type ON context_entries(entry_type);
            CREATE INDEX IF NOT EXISTS idx_ctx_tags ON context_entries(tags);
            CREATE INDEX IF NOT EXISTS idx_handoff_session ON agent_handoffs(session_id);
            CREATE INDEX IF NOT EXISTS idx_handoff_to ON agent_handoffs(to_agent);
            CREATE INDEX IF NOT EXISTS idx_state_session ON session_state(session_id);
        """)
        conn.commit()
        conn.close()

_init_context_db()


# ── Singleton access for the orchestrator to call directly ────────────────

def publish_agent_result(
    source_agent: str,
    action: str,
    result_data: dict[str, Any],
    success: bool,
    session_id: str = "global",
    target_agents: list[str] | None = None,
) -> str:
    """Called by the orchestrator after each agent execution.

    This is the glue that makes context sharing automatic — agents don't
    have to explicitly share; the orchestrator publishes on their behalf.
    """
    entry_id = f"ctx_{uuid.uuid4().hex[:12]}"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    targets = target_agents or ["*"]

    summary = result_data.get("message", f"{action} {'succeeded' if success else 'failed'}")
    entry = {
        "id": entry_id,
        "session_id": session_id,
        "source_agent": source_agent,
        "target_agents": targets,
        "entry_type": "result",
        "content": summary,
        "tags": [source_agent, action, "auto_published"],
        "priority": "high" if not success else "normal",
        "metadata": {
            "action": action,
            "success": success,
            "result_keys": list(result_data.keys()),
        },
        "created_at": now,
        "accessed_count": 0,
    }

    # Hot cache
    _hot_cache.setdefault(session_id, []).append(entry)

    # Persistent store
    with _lock:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO context_entries
               (id, session_id, source_agent, target_agents, entry_type,
                content, tags, priority, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry_id, session_id, source_agent,
                json.dumps(targets), "result",
                summary, json.dumps(entry["tags"]),
                entry["priority"], json.dumps(entry["metadata"]), now,
            ),
        )

        # Also record as a handoff so consuming agents can mark it read
        conn.execute(
            """INSERT INTO agent_handoffs
               (id, session_id, from_agent, to_agent, action_taken,
                result_summary, full_result, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                f"ho_{uuid.uuid4().hex[:12]}", session_id, source_agent,
                "*", action, summary, json.dumps(result_data), now,
            ),
        )
        conn.commit()
        conn.close()

    logger.info(
        "Published context: %s.%s → session=%s [%s]",
        source_agent, action, session_id, "success" if success else "failed",
    )
    return entry_id


def get_session_context(session_id: str = "global", for_agent: str = "") -> str:
    """Build a context string from shared memory for the system prompt.

    The orchestrator calls this to inject relevant cross-agent context
    into the LLM prompt so the model is aware of what other agents did.
    """
    entries = _hot_cache.get(session_id, [])
    if not entries:
        # Fall back to DB
        with _lock:
            conn = _get_conn()
            rows = conn.execute(
                """SELECT source_agent, entry_type, content, priority, created_at
                   FROM context_entries
                   WHERE session_id = ?
                   ORDER BY created_at DESC LIMIT 20""",
                (session_id,),
            ).fetchall()
            conn.close()
        entries = [dict(r) for r in rows]

    if not entries:
        return ""

    lines = ["## Shared Agent Context (this session)"]
    for e in entries[-15:]:
        source = e.get("source_agent", "?")
        content = e.get("content", "")
        priority = e.get("priority", "normal")
        marker = "🔴" if priority == "high" else "🔵"
        lines.append(f"- {marker} **{source}**: {content}")

    return "\n".join(lines)


# ── The Agent itself ──────────────────────────────────────────────────────

class ContextMemoryAgent(BaseAgent):
    """Shared inter-agent context memory bus.

    Allows any agent to store context that other agents can retrieve,
    enabling coordinated multi-agent workflows without explicit wiring.
    """

    agent_name = "context_memory_agent"

    def health_check(self) -> dict[str, Any]:
        with _lock:
            conn = _get_conn()
            ctx_count = conn.execute("SELECT COUNT(*) FROM context_entries").fetchone()[0]
            handoff_count = conn.execute("SELECT COUNT(*) FROM agent_handoffs").fetchone()[0]
            state_keys = conn.execute("SELECT COUNT(*) FROM session_state").fetchone()[0]
            conn.close()

        hot_entries = sum(len(v) for v in _hot_cache.values())
        return {
            "agent": self.agent_name,
            "type": "inter_agent_memory",
            "status": "ready",
            "context_entries": ctx_count,
            "handoffs_recorded": handoff_count,
            "session_state_keys": state_keys,
            "hot_cache_entries": hot_entries,
            "active_sessions": len(_hot_cache),
            "capabilities": [
                "store_context", "recall_context", "share_with_agent",
                "get_agent_context", "set_shared_state", "get_shared_state",
                "get_handoff_chain", "summarize_session",
            ],
        }

    # ── store_context ─────────────────────────────────────────────────

    def handle_store_context(
        self,
        content: str = "",
        source_agent: str = "",
        entry_type: str = "context",
        tags: list[str] | None = None,
        target_agents: list[str] | None = None,
        priority: str = "normal",
        session_id: str = "global",
        ttl_seconds: int = 0,
        metadata: dict[str, Any] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:
        """Store a context entry visible to other agents."""
        if not content:
            raise ValueError("'content' is required")

        entry_id = f"ctx_{uuid.uuid4().hex[:12]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tags = tags or []
        targets = target_agents or ["*"]
        expires = None
        if ttl_seconds > 0:
            expires = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(time.time() + ttl_seconds),
            )

        entry = {
            "id": entry_id,
            "session_id": session_id,
            "source_agent": source_agent or "unknown",
            "target_agents": targets,
            "entry_type": entry_type,
            "content": content,
            "tags": tags,
            "priority": priority,
            "metadata": metadata or {},
            "created_at": now,
            "expires_at": expires,
            "accessed_count": 0,
        }

        # Hot cache
        _hot_cache.setdefault(session_id, []).append(entry)

        # Persist
        with _lock:
            conn = _get_conn()
            conn.execute(
                """INSERT INTO context_entries
                   (id, session_id, source_agent, target_agents, entry_type,
                    content, tags, priority, metadata, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_id, session_id, entry["source_agent"],
                    json.dumps(targets), entry_type, content,
                    json.dumps(tags), priority,
                    json.dumps(entry["metadata"]), now, expires,
                ),
            )
            conn.commit()
            conn.close()

        logger.info("Context stored: %s from %s [%s]", entry_id, source_agent, entry_type)
        return {
            "message": f"Context stored ({entry_type}) from {source_agent or 'unknown'}",
            "entry_id": entry_id,
            "tags": tags,
            "visible_to": targets,
            "expires_at": expires,
        }

    # ── recall_context ────────────────────────────────────────────────

    def handle_recall_context(
        self,
        query: str = "",
        tags: list[str] | None = None,
        source_agent: str = "",
        entry_type: str = "",
        session_id: str = "global",
        limit: int = 20,
        **kw: Any,
    ) -> dict[str, Any]:
        """Recall context entries, optionally filtered by tags/source/type."""
        with _lock:
            conn = _get_conn()

            sql = """SELECT * FROM context_entries
                     WHERE session_id = ?
                     AND (expires_at IS NULL OR expires_at > ?)"""
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            params: list[Any] = [session_id, now]

            if query:
                sql += " AND content LIKE ?"
                params.append(f"%{query}%")
            if source_agent:
                sql += " AND source_agent = ?"
                params.append(source_agent)
            if entry_type:
                sql += " AND entry_type = ?"
                params.append(entry_type)
            if tags:
                for tag in tags:
                    sql += " AND tags LIKE ?"
                    params.append(f"%{tag}%")

            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()

            # Update access counts
            for row in rows:
                conn.execute(
                    "UPDATE context_entries SET accessed_count = accessed_count + 1, last_accessed = ? WHERE id = ?",
                    (now, row["id"]),
                )
            conn.commit()
            conn.close()

        entries = [
            {
                "id": r["id"],
                "source_agent": r["source_agent"],
                "entry_type": r["entry_type"],
                "content": r["content"],
                "tags": json.loads(r["tags"]),
                "priority": r["priority"],
                "created_at": r["created_at"],
                "accessed_count": r["accessed_count"] + 1,
            }
            for r in rows
        ]

        return {
            "message": f"Recalled {len(entries)} context entries",
            "query": query,
            "entries": entries,
            "session_id": session_id,
        }

    # ── share_with_agent ──────────────────────────────────────────────

    def handle_share_with_agent(
        self,
        from_agent: str = "",
        to_agent: str = "",
        content: str = "",
        action_context: str = "",
        priority: str = "normal",
        session_id: str = "global",
        **kw: Any,
    ) -> dict[str, Any]:
        """Explicitly share context from one agent to another.

        Unlike broadcast context, this creates a directed handoff that
        the receiving agent can acknowledge.
        """
        if not from_agent or not to_agent or not content:
            raise ValueError("'from_agent', 'to_agent', and 'content' are required")

        handoff_id = f"ho_{uuid.uuid4().hex[:12]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with _lock:
            conn = _get_conn()
            conn.execute(
                """INSERT INTO agent_handoffs
                   (id, session_id, from_agent, to_agent, action_taken,
                    result_summary, full_result, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    handoff_id, session_id, from_agent, to_agent,
                    action_context or "context_share",
                    content, json.dumps({"priority": priority}), now,
                ),
            )
            conn.commit()
            conn.close()

        # Also store in the general context so it appears in session context
        self.handle_store_context(
            content=f"[{from_agent} → {to_agent}] {content}",
            source_agent=from_agent,
            entry_type="handoff",
            tags=[from_agent, to_agent, "handoff"],
            target_agents=[to_agent],
            priority=priority,
            session_id=session_id,
        )

        logger.info("Handoff: %s → %s (%s)", from_agent, to_agent, handoff_id)
        return {
            "message": f"Context shared: {from_agent} → {to_agent}",
            "handoff_id": handoff_id,
            "from": from_agent,
            "to": to_agent,
        }

    # ── get_agent_context ─────────────────────────────────────────────

    def handle_get_agent_context(
        self,
        agent_name: str = "",
        session_id: str = "global",
        include_broadcasts: bool = True,
        **kw: Any,
    ) -> dict[str, Any]:
        """Get all context relevant to a specific agent.

        Includes:
          - Entries explicitly targeted at this agent
          - Broadcast entries (target_agents = ["*"])
          - Unconsumed handoffs addressed to this agent
        """
        if not agent_name:
            raise ValueError("'agent_name' is required")

        with _lock:
            conn = _get_conn()
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            # Targeted + broadcast context
            if include_broadcasts:
                ctx_rows = conn.execute(
                    """SELECT * FROM context_entries
                       WHERE session_id = ?
                       AND (target_agents LIKE ? OR target_agents LIKE ?)
                       AND (expires_at IS NULL OR expires_at > ?)
                       ORDER BY created_at DESC LIMIT 30""",
                    (session_id, f'%"{agent_name}"%', '%"*"%', now),
                ).fetchall()
            else:
                ctx_rows = conn.execute(
                    """SELECT * FROM context_entries
                       WHERE session_id = ?
                       AND target_agents LIKE ?
                       AND (expires_at IS NULL OR expires_at > ?)
                       ORDER BY created_at DESC LIMIT 30""",
                    (session_id, f'%"{agent_name}"%', now),
                ).fetchall()

            # Pending handoffs to this agent
            handoff_rows = conn.execute(
                """SELECT * FROM agent_handoffs
                   WHERE session_id = ? AND (to_agent = ? OR to_agent = '*')
                   AND consumed = 0
                   ORDER BY created_at DESC LIMIT 10""",
                (session_id, agent_name),
            ).fetchall()

            # Mark handoffs as consumed
            for h in handoff_rows:
                conn.execute(
                    "UPDATE agent_handoffs SET consumed = 1 WHERE id = ?",
                    (h["id"],),
                )
            conn.commit()
            conn.close()

        context = [
            {
                "source": r["source_agent"],
                "type": r["entry_type"],
                "content": r["content"],
                "priority": r["priority"],
                "tags": json.loads(r["tags"]),
                "created_at": r["created_at"],
            }
            for r in ctx_rows
        ]

        handoffs = [
            {
                "from": r["from_agent"],
                "action": r["action_taken"],
                "summary": r["result_summary"],
                "created_at": r["created_at"],
            }
            for r in handoff_rows
        ]

        return {
            "message": f"Context for '{agent_name}': {len(context)} entries, {len(handoffs)} pending handoffs",
            "agent": agent_name,
            "context": context,
            "pending_handoffs": handoffs,
            "session_id": session_id,
        }

    # ── set / get shared state ────────────────────────────────────────

    def handle_set_shared_state(
        self,
        key: str = "",
        value: Any = None,
        session_id: str = "global",
        **kw: Any,
    ) -> dict[str, Any]:
        """Set a shared key-value pair visible to all agents.

        Useful for flags, counters, and configuration that multiple
        agents need to coordinate on (e.g., "deployment_in_progress": true).
        """
        if not key:
            raise ValueError("'key' is required")

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        serialized = json.dumps(value) if not isinstance(value, str) else value

        with _lock:
            conn = _get_conn()
            conn.execute(
                """INSERT INTO session_state (session_id, key, value, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(session_id, key)
                   DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                (session_id, key, serialized, now),
            )
            conn.commit()
            conn.close()

        return {
            "message": f"Shared state set: {key}",
            "key": key,
            "value": value,
            "session_id": session_id,
        }

    def handle_get_shared_state(
        self,
        key: str = "",
        session_id: str = "global",
        **kw: Any,
    ) -> dict[str, Any]:
        """Get shared state — all keys if no key specified."""
        with _lock:
            conn = _get_conn()
            if key:
                row = conn.execute(
                    "SELECT * FROM session_state WHERE session_id = ? AND key = ?",
                    (session_id, key),
                ).fetchone()
                conn.close()
                if not row:
                    return {"message": f"Key '{key}' not found", "key": key, "value": None}
                try:
                    val = json.loads(row["value"])
                except (json.JSONDecodeError, TypeError):
                    val = row["value"]
                return {"key": key, "value": val, "updated_at": row["updated_at"]}
            else:
                rows = conn.execute(
                    "SELECT * FROM session_state WHERE session_id = ? ORDER BY key",
                    (session_id,),
                ).fetchall()
                conn.close()
                state = {}
                for r in rows:
                    try:
                        state[r["key"]] = json.loads(r["value"])
                    except (json.JSONDecodeError, TypeError):
                        state[r["key"]] = r["value"]
                return {
                    "message": f"Shared state: {len(state)} keys",
                    "state": state,
                    "session_id": session_id,
                }

    # ── get_handoff_chain ─────────────────────────────────────────────

    def handle_get_handoff_chain(
        self,
        session_id: str = "global",
        limit: int = 30,
        **kw: Any,
    ) -> dict[str, Any]:
        """Show the full chain of agent handoffs in this session.

        Useful for debugging multi-agent workflows and understanding
        how context flowed between agents.
        """
        with _lock:
            conn = _get_conn()
            rows = conn.execute(
                """SELECT from_agent, to_agent, action_taken, result_summary,
                          created_at, consumed
                   FROM agent_handoffs
                   WHERE session_id = ?
                   ORDER BY created_at ASC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
            conn.close()

        chain = [
            {
                "from": r["from_agent"],
                "to": r["to_agent"],
                "action": r["action_taken"],
                "summary": r["result_summary"],
                "time": r["created_at"],
                "consumed": bool(r["consumed"]),
            }
            for r in rows
        ]

        # Build a visual chain
        flow = " → ".join(
            f"{h['from']}({h['action']})" for h in chain
        )

        return {
            "message": f"Handoff chain: {len(chain)} steps",
            "chain": chain,
            "flow_summary": flow or "(empty)",
            "session_id": session_id,
        }

    # ── summarize_session ─────────────────────────────────────────────

    def handle_summarize_session(
        self,
        session_id: str = "global",
        **kw: Any,
    ) -> dict[str, Any]:
        """Summarize all shared context in the current session.

        Provides a structured overview of what happened, which agents
        were involved, and the key findings.
        """
        with _lock:
            conn = _get_conn()

            # Context stats
            ctx_stats = conn.execute(
                """SELECT source_agent, entry_type, COUNT(*) as cnt
                   FROM context_entries WHERE session_id = ?
                   GROUP BY source_agent, entry_type""",
                (session_id,),
            ).fetchall()

            # Handoff stats
            handoff_count = conn.execute(
                "SELECT COUNT(*) FROM agent_handoffs WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]

            # Recent entries for summary
            recent = conn.execute(
                """SELECT source_agent, content, priority
                   FROM context_entries WHERE session_id = ?
                   ORDER BY created_at DESC LIMIT 10""",
                (session_id,),
            ).fetchall()

            # Shared state
            state_count = conn.execute(
                "SELECT COUNT(*) FROM session_state WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]

            conn.close()

        # Build summary
        agents_involved = set()
        by_type: dict[str, int] = {}
        for row in ctx_stats:
            agents_involved.add(row["source_agent"])
            by_type[row["entry_type"]] = by_type.get(row["entry_type"], 0) + row["cnt"]

        total_entries = sum(by_type.values())
        highlights = [
            {"agent": r["source_agent"], "content": r["content"], "priority": r["priority"]}
            for r in recent
        ]

        return {
            "message": f"Session '{session_id}': {total_entries} entries, {len(agents_involved)} agents, {handoff_count} handoffs",
            "session_id": session_id,
            "total_entries": total_entries,
            "agents_involved": sorted(agents_involved),
            "entries_by_type": by_type,
            "handoffs": handoff_count,
            "shared_state_keys": state_count,
            "recent_highlights": highlights,
            "hot_cache_entries": len(_hot_cache.get(session_id, [])),
        }
