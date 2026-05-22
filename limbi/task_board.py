from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def _db_path() -> Path:
    raw = os.getenv("TASK_BOARD_DB_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    workspace_root = Path(os.getenv("LIMBI_WORKSPACE_ROOT") or Path.cwd()).expanduser().resolve()
    return workspace_root / ".limbi" / "task_board.db"


def _get_conn() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    with _lock:
        conn = _get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS task_boards (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_items (
                id TEXT PRIMARY KEY,
                board_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                workstream_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                action_name TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                terminal_label TEXT DEFAULT '',
                heartbeat_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finished_at TEXT,
                payload TEXT DEFAULT '{}',
                result TEXT DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_task_items_board ON task_items(board_id);
            CREATE INDEX IF NOT EXISTS idx_task_items_session ON task_items(session_id);
            CREATE INDEX IF NOT EXISTS idx_task_items_status ON task_items(status);
            CREATE INDEX IF NOT EXISTS idx_task_items_heartbeat ON task_items(heartbeat_at);
            """
        )
        conn.commit()
        conn.close()


_init_db()


def ensure_board(session_id: str, title: str | None = None) -> str:
    title = title or f"Session {session_id}"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _lock:
        conn = _get_conn()
        row = conn.execute(
            "SELECT id FROM task_boards WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if row:
            conn.close()
            return str(row["id"])
        board_id = f"board_{uuid.uuid4().hex[:12]}"
        conn.execute(
            "INSERT INTO task_boards (id, session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (board_id, session_id, title, now, now),
        )
        conn.commit()
        conn.close()
    return board_id


def start_task(
    session_id: str,
    agent_name: str,
    action_name: str,
    *,
    title: str = "",
    workstream_id: str | None = None,
    terminal_label: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    board_id = ensure_board(session_id)
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    workstream_id = workstream_id or f"ws_{uuid.uuid4().hex[:8]}"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record = {
        "id": task_id,
        "board_id": board_id,
        "session_id": session_id,
        "workstream_id": workstream_id,
        "agent_name": agent_name,
        "action_name": action_name,
        "title": title or f"{agent_name}.{action_name}",
        "status": "running",
        "terminal_label": terminal_label or workstream_id,
        "heartbeat_at": now,
        "created_at": now,
        "updated_at": now,
        "finished_at": None,
        "payload": payload or {},
        "result": {},
    }
    with _lock:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO task_items
               (id, board_id, session_id, workstream_id, agent_name, action_name,
                title, status, terminal_label, heartbeat_at, created_at, updated_at,
                finished_at, payload, result)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_id,
                board_id,
                session_id,
                workstream_id,
                agent_name,
                action_name,
                record["title"],
                record["status"],
                record["terminal_label"],
                now,
                now,
                now,
                None,
                json.dumps(record["payload"]),
                "{}",
            ),
        )
        conn.commit()
        conn.close()
    return record


def heartbeat_task(task_id: str, *, note: str = "", status: str | None = None) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _lock:
        conn = _get_conn()
        updates = ["heartbeat_at = ?", "updated_at = ?"]
        params: list[Any] = [now, now]
        if status:
            updates.append("status = ?")
            params.append(status)
        if note:
            updates.append("terminal_label = ?")
            params.append(note[:120])
        params.append(task_id)
        conn.execute(
            f"UPDATE task_items SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        conn.close()


def finish_task(task_id: str, *, success: bool, result: dict[str, Any] | None = None, note: str = "") -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _lock:
        conn = _get_conn()
        conn.execute(
            """UPDATE task_items
               SET status = ?, heartbeat_at = ?, updated_at = ?, finished_at = ?, result = ?, terminal_label = ?
               WHERE id = ?""",
            (
                "done" if success else "failed",
                now,
                now,
                now,
                json.dumps(result or {}),
                note[:120],
                task_id,
            ),
        )
        conn.commit()
        conn.close()


def list_tasks(session_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with _lock:
        conn = _get_conn()
        sql = "SELECT * FROM task_items"
        params: list[Any] = []
        clauses: list[str] = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
    return [dict(r) for r in rows]


def zombie_tasks(*, stale_seconds: int = 300) -> list[dict[str, Any]]:
    cutoff = time.time() - max(1, stale_seconds)
    zombies: list[dict[str, Any]] = []
    for row in list_tasks(limit=200):
        heartbeat = row.get("heartbeat_at") or ""
        try:
            ts = time.mktime(time.strptime(heartbeat, "%Y-%m-%dT%H:%M:%SZ"))
        except Exception:
            continue
        if row.get("status") == "running" and ts < cutoff:
            zombies.append(row)
    return zombies


def board_snapshot(session_id: str | None = None) -> dict[str, Any]:
    tasks = list_tasks(session_id=session_id, limit=100)
    columns: dict[str, list[dict[str, Any]]] = {"todo": [], "running": [], "done": [], "failed": []}
    for task in tasks:
        columns.setdefault(task.get("status") or "todo", []).append(task)
    return {
        "boards": len({task["board_id"] for task in tasks}),
        "tasks": len(tasks),
        "columns": columns,
        "zombies": zombie_tasks(),
    }
