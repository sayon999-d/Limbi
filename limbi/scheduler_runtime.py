from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any

from .workspace import get_workspace_path

_lock = threading.Lock()


def _db_path() -> Path:
    raw = os.getenv("SCHEDULER_DB_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return get_workspace_path() / "scheduler.db"


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
            CREATE TABLE IF NOT EXISTS scheduler_jobs (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                name TEXT NOT NULL,
                natural_spec TEXT NOT NULL,
                cron_expression TEXT NOT NULL,
                prompt TEXT NOT NULL,
                delivery_target TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_run_at TEXT,
                next_run_at TEXT,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS scheduler_runs (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                run_at TEXT NOT NULL,
                status TEXT NOT NULL,
                output TEXT DEFAULT '',
                error TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_session ON scheduler_jobs(session_id);
            CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_enabled ON scheduler_jobs(enabled);
            CREATE INDEX IF NOT EXISTS idx_scheduler_runs_job ON scheduler_runs(job_id);
            """
        )
        conn.commit()
        conn.close()


_init_db()


def parse_natural_schedule(text: str) -> dict[str, Any]:
    raw = (text or "").strip().lower()
    result = {
        "natural_spec": text.strip() if text else "",
        "cron_expression": "0 * * * *",
        "confidence": 0.3,
        "notes": ["Defaulting to hourly cadence"],
    }
    if not raw:
        return result
    if "every minute" in raw or "minutely" in raw:
        result.update({"cron_expression": "* * * * *", "confidence": 0.95, "notes": ["Every minute"]})
    elif "every hour" in raw or "hourly" in raw:
        result.update({"cron_expression": "0 * * * *", "confidence": 0.95, "notes": ["Hourly"]})
    elif "daily" in raw or "every day" in raw:
        result.update({"cron_expression": "0 9 * * *", "confidence": 0.9, "notes": ["Daily at 09:00"]})
    elif "weekly" in raw or "every week" in raw:
        result.update({"cron_expression": "0 9 * * 1", "confidence": 0.88, "notes": ["Weekly on Monday at 09:00"]})
    elif "every 2 hours" in raw or "every two hours" in raw:
        result.update({"cron_expression": "0 */2 * * *", "confidence": 0.93, "notes": ["Every two hours"]})
    else:
        at_match = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", raw)
        every_match = re.search(r"every\s+(\d+)\s+(minute|hour|day|week)s?", raw)
        if every_match:
            amount = int(every_match.group(1))
            unit = every_match.group(2)
            if unit == "minute":
                result.update({"cron_expression": f"*/{max(1, amount)} * * * *", "confidence": 0.8})
            elif unit == "hour":
                result.update({"cron_expression": f"0 */{max(1, amount)} * * *", "confidence": 0.8})
            elif unit == "day":
                result.update({"cron_expression": "0 9 */1 * *", "confidence": 0.8})
            else:
                result.update({"cron_expression": "0 9 * * 1", "confidence": 0.8})
        elif at_match:
            hour = int(at_match.group(1)) % 24
            minute = int(at_match.group(2) or 0)
            suffix = (at_match.group(3) or "").lower()
            if suffix == "pm" and hour < 12:
                hour += 12
            if suffix == "am" and hour == 12:
                hour = 0
            result.update(
                {
                    "cron_expression": f"{minute} {hour} * * *",
                    "confidence": 0.82,
                    "notes": [f"Daily at {hour:02d}:{minute:02d}"],
                }
            )
    return result


def _next_run_at_from_spec(spec: str) -> str:
    now = datetime.utcnow()
    raw = (spec or "").strip().lower()
    if "every minute" in raw or "minutely" in raw:
        dt = now + timedelta(minutes=1)
    elif "every hour" in raw or "hourly" in raw or "every 2 hours" in raw or "every two hours" in raw:
        hours = 2 if "2 hour" in raw or "two hour" in raw else 1
        dt = now + timedelta(hours=hours)
    elif "daily" in raw or "every day" in raw:
        dt = now + timedelta(days=1)
    elif "weekly" in raw or "every week" in raw:
        dt = now + timedelta(days=7)
    else:
        at_match = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", raw)
        if at_match:
            hour = int(at_match.group(1)) % 24
            minute = int(at_match.group(2) or 0)
            suffix = (at_match.group(3) or "").lower()
            if suffix == "pm" and hour < 12:
                hour += 12
            if suffix == "am" and hour == 12:
                hour = 0
            dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if dt <= now:
                dt += timedelta(days=1)
        else:
            dt = now + timedelta(hours=1)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_run_hint(cron_expression: str) -> str:
    return _next_run_at_from_spec(cron_expression)


def create_job(
    *,
    session_id: str,
    name: str,
    prompt: str,
    delivery_target: str = "local",
    natural_spec: str = "",
    cron_expression: str = "",
    enabled: bool = True,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parse_result = parse_natural_schedule(natural_spec or cron_expression or "hourly")
    cron = cron_expression or parse_result["cron_expression"]
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    job = {
        "id": job_id,
        "session_id": session_id,
        "name": name,
        "natural_spec": natural_spec or prompt,
        "cron_expression": cron,
        "prompt": prompt,
        "delivery_target": delivery_target,
        "enabled": bool(enabled),
        "created_at": now,
        "updated_at": now,
        "last_run_at": None,
        "next_run_at": _next_run_hint(natural_spec or cron),
        "metadata": metadata or {},
    }
    with _lock:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO scheduler_jobs
               (id, session_id, name, natural_spec, cron_expression, prompt, delivery_target,
                enabled, created_at, updated_at, last_run_at, next_run_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                session_id,
                name,
                job["natural_spec"],
                cron,
                prompt,
                delivery_target,
                1 if enabled else 0,
                now,
                now,
                None,
                job["next_run_at"],
                json.dumps(job["metadata"]),
            ),
        )
        conn.commit()
        conn.close()
    return job


def list_jobs(session_id: str | None = None) -> list[dict[str, Any]]:
    with _lock:
        conn = _get_conn()
        if session_id:
            rows = conn.execute(
                "SELECT * FROM scheduler_jobs WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM scheduler_jobs ORDER BY created_at DESC").fetchall()
        conn.close()
    jobs: list[dict[str, Any]] = []
    for row in rows:
        job = dict(row)
        try:
            job["metadata"] = json.loads(job.get("metadata") or "{}")
        except Exception:
            job["metadata"] = {}
        jobs.append(job)
    return jobs


def record_run(job_id: str, session_id: str, status: str, output: str = "", error: str = "") -> dict[str, Any]:
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _lock:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO scheduler_runs (id, job_id, session_id, run_at, status, output, error)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, job_id, session_id, now, status, output, error),
        )
        conn.execute(
            "UPDATE scheduler_jobs SET last_run_at = ?, updated_at = ? WHERE id = ?",
            (now, now, job_id),
        )
        conn.commit()
        conn.close()
    return {"id": run_id, "job_id": job_id, "session_id": session_id, "status": status, "run_at": now}


def list_due_jobs(session_id: str | None = None) -> list[dict[str, Any]]:
    now = datetime.utcnow()
    jobs = list_jobs(session_id=session_id)
    due: list[dict[str, Any]] = []
    for job in jobs:
        if not int(job.get("enabled", 1) or 0):
            continue
        next_run = str(job.get("next_run_at") or "").strip()
        try:
            due_at = datetime.strptime(next_run, "%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            continue
        if due_at <= now:
            due.append(job)
    return due
