

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("limbi.audit")

_DB_PATH = os.getenv("AUDIT_DB_PATH", "./limbi_audit.db")
_lock = threading.Lock()
_REDACTED = "[REDACTED]"
_SENSITIVE_KEYWORDS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
    "credential",
    "private_key",
    "client_secret",
    "session",
)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in _SENSITIVE_KEYWORDS)


def _redact_string(value: str) -> str:
    redacted = value
    redacted = re.sub(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-+/=]+", r"\1[REDACTED]", redacted)
    for token in ("api_key", "apikey", "token", "secret", "password", "passwd", "authorization"):
        redacted = re.sub(
            rf"(?i)\b({token}\b\s*[:=]\s*)([^\s,;]+)",
            rf"\1[REDACTED]",
            redacted,
        )
    return redacted


def _sanitize_for_audit(value: Any, key: str | None = None) -> Any:
    if key and _is_sensitive_key(key):
        return _REDACTED
    if isinstance(value, dict):
        return {k: _sanitize_for_audit(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_audit(item, key) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_audit(item, key) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def _sanitize_json_text(text: str | None) -> str:
    if not text:
        return "{}"
    try:
        loaded = json.loads(text)
    except Exception:
        return _redact_string(str(text))
    return json.dumps(_sanitize_for_audit(loaded))

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db() -> None:

    with _lock:
        conn = _get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS execution_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                agent       TEXT NOT NULL,
                action      TEXT NOT NULL,
                params      TEXT DEFAULT '{}',
                success     INTEGER NOT NULL DEFAULT 0,
                result_data TEXT DEFAULT '{}',
                error       TEXT,
                duration_ms REAL DEFAULT 0,
                source      TEXT DEFAULT 'orchestrator'
            );

            CREATE TABLE IF NOT EXISTS webhook_results (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                agent       TEXT NOT NULL,
                action      TEXT NOT NULL,
                correlation_id TEXT,
                payload     TEXT DEFAULT '{}',
                status      TEXT DEFAULT 'received'
            );

            CREATE INDEX IF NOT EXISTS idx_exec_agent ON execution_log(agent);
            CREATE INDEX IF NOT EXISTS idx_exec_ts ON execution_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_webhook_corr ON webhook_results(correlation_id);
        """)
        conn.commit()
        conn.close()
        logger.info("Audit DB initialized at %s", _DB_PATH)

def log_execution(
    agent: str,
    action: str,
    params: dict[str, Any],
    success: bool,
    result_data: dict[str, Any] | None = None,
    error: str | None = None,
    duration_ms: float = 0.0,
    source: str = "orchestrator",
) -> int:

    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """INSERT INTO execution_log
               (timestamp, agent, action, params, success, result_data, error, duration_ms, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                agent,
                action,
                json.dumps(_sanitize_for_audit(params)),
                int(success),
                json.dumps(_sanitize_for_audit(result_data or {})),
                _redact_string(error) if error else None,
                duration_ms,
                source,
            ),
        )
        conn.commit()
        row_id = cursor.lastrowid
        conn.close()
    logger.debug("Audit log #%d: %s.%s success=%s", row_id, agent, action, success)
    return row_id

def log_webhook(
    agent: str,
    action: str,
    correlation_id: str | None,
    payload: dict[str, Any],
    status: str = "received",
) -> int:

    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """INSERT INTO webhook_results
               (timestamp, agent, action, correlation_id, payload, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                agent,
                action,
                correlation_id,
                json.dumps(_sanitize_for_audit(payload)),
                status,
            ),
        )
        conn.commit()
        row_id = cursor.lastrowid
        conn.close()
    return row_id

def get_recent_executions(limit: int = 20) -> list[dict[str, Any]]:

    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM execution_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
    sanitized_rows: list[dict[str, Any]] = []
    for row in rows:
        entry = dict(row)
        entry["params"] = _sanitize_json_text(entry.get("params"))
        entry["result_data"] = _sanitize_json_text(entry.get("result_data"))
        if entry.get("error"):
            entry["error"] = _redact_string(str(entry["error"]))
        sanitized_rows.append(entry)
    return sanitized_rows

def get_execution_stats() -> dict[str, Any]:

    with _lock:
        conn = _get_conn()
        total = conn.execute("SELECT COUNT(*) FROM execution_log").fetchone()[0]
        successes = conn.execute(
            "SELECT COUNT(*) FROM execution_log WHERE success = 1"
        ).fetchone()[0]
        by_agent = conn.execute(
            "SELECT agent, COUNT(*) as cnt, SUM(success) as ok FROM execution_log GROUP BY agent"
        ).fetchall()
        avg_duration = conn.execute(
            "SELECT AVG(duration_ms) FROM execution_log WHERE duration_ms > 0"
        ).fetchone()[0]
        conn.close()

    return {
        "total_executions": total,
        "successful": successes,
        "failed": total - successes,
        "success_rate": f"{(successes / max(total, 1)) * 100:.1f}%",
        "avg_duration_ms": round(avg_duration or 0, 1),
        "by_agent": [
            {"agent": r["agent"], "total": r["cnt"], "successful": r["ok"]}
            for r in by_agent
        ],
    }
