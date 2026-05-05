

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any

from . import BaseAgent

logger = logging.getLogger("limbi.agents.memory")

_MEM_DB_PATH = os.getenv("MEMORY_DB_PATH", "./limbi_memory.db")
_lock = threading.Lock()

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_MEM_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def _init_memory_db() -> None:
    with _lock:
        conn = _get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS long_term_memory (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                category    TEXT NOT NULL DEFAULT 'general',
                key         TEXT NOT NULL,
                content     TEXT NOT NULL,
                importance  REAL DEFAULT 0.5,
                access_count INTEGER DEFAULT 0,
                last_accessed TEXT,
                metadata    TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS short_term_memory (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                role        TEXT NOT NULL DEFAULT 'system',
                content     TEXT NOT NULL,
                session_id  TEXT DEFAULT 'default'
            );

            CREATE TABLE IF NOT EXISTS memory_summaries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                summary     TEXT NOT NULL,
                source_ids  TEXT DEFAULT '[]',
                session_id  TEXT DEFAULT 'default'
            );

            CREATE INDEX IF NOT EXISTS idx_ltm_category ON long_term_memory(category);
            CREATE INDEX IF NOT EXISTS idx_ltm_key ON long_term_memory(key);
            CREATE INDEX IF NOT EXISTS idx_ltm_importance ON long_term_memory(importance DESC);
            CREATE INDEX IF NOT EXISTS idx_stm_session ON short_term_memory(session_id);
        """)
        conn.commit()
        conn.close()

_init_memory_db()

class MemoryAgent(BaseAgent):

    agent_name = "memory_agent"

    def health_check(self) -> dict[str, Any]:
        with _lock:
            conn = _get_conn()
            ltm_count = conn.execute("SELECT COUNT(*) FROM long_term_memory").fetchone()[0]
            stm_count = conn.execute("SELECT COUNT(*) FROM short_term_memory").fetchone()[0]
            summaries = conn.execute("SELECT COUNT(*) FROM memory_summaries").fetchone()[0]
            conn.close()
        return {
            "agent": self.agent_name,
            "type": "memory_augmented",
            "status": "ready",
            "long_term_entries": ltm_count,
            "short_term_entries": stm_count,
            "summaries": summaries,
            "db_path": _MEM_DB_PATH,
        }

    def handle_remember(
        self,
        key: str = "",
        content: str = "",
        category: str = "general",
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        if not key or not content:
            raise ValueError("Both 'key' and 'content' are required")

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with _lock:
            conn = _get_conn()

            existing = conn.execute(
                "SELECT id FROM long_term_memory WHERE key = ? AND category = ?",
                (key, category)
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE long_term_memory SET content = ?, importance = ?, timestamp = ?, metadata = ? WHERE id = ?",
                    (content, importance, now, json.dumps(metadata or {}), existing["id"]),
                )
                action = "updated"
            else:
                conn.execute(
                    "INSERT INTO long_term_memory (timestamp, category, key, content, importance, last_accessed, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (now, category, key, content, importance, now, json.dumps(metadata or {})),
                )
                action = "stored"
            conn.commit()
            conn.close()

        logger.info("Memory %s: [%s] %s", action, category, key)
        return {
            "message": f"Memory {action}: '{key}' in category '{category}'",
            "key": key,
            "category": category,
            "importance": importance,
            "action": action,
        }

    def handle_recall(
        self,
        query: str = "",
        category: str = "",
        limit: int = 10,
        min_importance: float = 0.0,
        **kw: Any,
    ) -> dict[str, Any]:

        with _lock:
            conn = _get_conn()

            sql = "SELECT * FROM long_term_memory WHERE importance >= ?"
            params: list[Any] = [min_importance]

            if category:
                sql += " AND category = ?"
                params.append(category)

            if query:
                sql += " AND (key LIKE ? OR content LIKE ?)"
                params.extend([f"%{query}%", f"%{query}%"])

            sql += " ORDER BY importance DESC, timestamp DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()

            for row in rows:
                conn.execute(
                    "UPDATE long_term_memory SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                    (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), row["id"]),
                )
            conn.commit()
            conn.close()

        memories = [
            {
                "id": r["id"],
                "key": r["key"],
                "content": r["content"],
                "category": r["category"],
                "importance": r["importance"],
                "access_count": r["access_count"],
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]

        return {
            "message": f"Found {len(memories)} memories",
            "query": query,
            "memories": memories,
        }

    def handle_forget(
        self,
        key: str = "",
        category: str = "",
        older_than_days: int = 0,
        min_importance_below: float = 0.0,
        **kw: Any,
    ) -> dict[str, Any]:

        with _lock:
            conn = _get_conn()
            deleted = 0

            if key:
                cursor = conn.execute("DELETE FROM long_term_memory WHERE key = ?", (key,))
                deleted = cursor.rowcount
            elif older_than_days > 0 and min_importance_below > 0:
                cursor = conn.execute(
                    "DELETE FROM long_term_memory WHERE importance < ? AND timestamp < datetime('now', ?)",
                    (min_importance_below, f"-{older_than_days} days"),
                )
                deleted = cursor.rowcount
            elif category:
                cursor = conn.execute("DELETE FROM long_term_memory WHERE category = ?", (category,))
                deleted = cursor.rowcount

            conn.commit()
            conn.close()

        return {
            "message": f"Evicted {deleted} memories",
            "criteria": {"key": key, "category": category, "older_than_days": older_than_days},
            "deleted_count": deleted,
        }

    def handle_note(
        self,
        content: str = "",
        role: str = "system",
        session_id: str = "default",
        **kw: Any,
    ) -> dict[str, Any]:

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with _lock:
            conn = _get_conn()
            conn.execute(
                "INSERT INTO short_term_memory (timestamp, role, content, session_id) VALUES (?, ?, ?, ?)",
                (now, role, content, session_id),
            )
            conn.commit()
            conn.close()

        return {"message": "Note added to short-term memory", "session_id": session_id}

    def handle_get_context(
        self,
        session_id: str = "default",
        limit: int = 20,
        **kw: Any,
    ) -> dict[str, Any]:

        with _lock:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT * FROM short_term_memory WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
            conn.close()

        return {
            "session_id": session_id,
            "entries": [
                {"role": r["role"], "content": r["content"], "timestamp": r["timestamp"]}
                for r in reversed(rows)
            ],
            "count": len(rows),
        }

    def handle_get_stats(self, **kw: Any) -> dict[str, Any]:

        with _lock:
            conn = _get_conn()
            ltm = conn.execute("SELECT COUNT(*), AVG(importance), SUM(access_count) FROM long_term_memory").fetchone()
            categories = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM long_term_memory GROUP BY category"
            ).fetchall()
            stm = conn.execute("SELECT COUNT(*) FROM short_term_memory").fetchone()
            most_accessed = conn.execute(
                "SELECT key, access_count FROM long_term_memory ORDER BY access_count DESC LIMIT 5"
            ).fetchall()
            conn.close()

        return {
            "long_term": {
                "total_entries": ltm[0],
                "avg_importance": round(ltm[1] or 0, 2),
                "total_accesses": ltm[2] or 0,
                "categories": {r["category"]: r["cnt"] for r in categories},
            },
            "short_term": {
                "total_entries": stm[0],
            },
            "most_accessed": [{"key": r["key"], "accesses": r["access_count"]} for r in most_accessed],
        }

    def handle_consolidate(
        self,
        session_id: str = "default",
        **kw: Any,
    ) -> dict[str, Any]:

        with _lock:
            conn = _get_conn()
            stm_rows = conn.execute(
                "SELECT * FROM short_term_memory WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()

            if len(stm_rows) < 5:
                conn.close()
                return {"message": "Not enough short-term entries to consolidate (need 5)"}

            contents = [r["content"] for r in stm_rows]
            summary = f"Session '{session_id}' summary ({len(contents)} entries): " + " | ".join(
                c[:80] for c in contents[:10]
            )

            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            source_ids = [r["id"] for r in stm_rows]
            conn.execute(
                "INSERT INTO memory_summaries (timestamp, summary, source_ids, session_id) VALUES (?, ?, ?, ?)",
                (now, summary, json.dumps(source_ids), session_id),
            )

            conn.execute(
                "DELETE FROM short_term_memory WHERE session_id = ? AND id <= ?",
                (session_id, max(source_ids)),
            )
            conn.commit()
            conn.close()

        return {
            "message": f"Consolidated {len(stm_rows)} short-term memories into summary",
            "summary": summary,
            "entries_cleared": len(stm_rows),
            "session_id": session_id,
        }
