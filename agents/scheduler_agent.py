

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.scheduler")

_schedules: dict[str, dict[str, Any]] = {}
_reminders: list[dict[str, Any]] = []
_deadlines: list[dict[str, Any]] = []

class SchedulerAgent(BaseAgent):

    agent_name = "scheduler_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "scheduler",
            "status": "ready",
            "active_schedules": len(_schedules),
            "pending_reminders": len([r for r in _reminders if r["status"] == "pending"]),
            "tracked_deadlines": len(_deadlines),
        }

    def handle_create_reminder(
        self,
        title: str = "",
        message: str = "",
        remind_at: str = "",
        priority: str = "normal",
        **kw: Any,
    ) -> dict[str, Any]:

        if not title:
            raise ValueError("A reminder 'title' is required")

        reminder = {
            "id": str(uuid.uuid4())[:8],
            "title": title,
            "message": message,
            "remind_at": remind_at or "not_set",
            "priority": priority,
            "status": "pending",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        _reminders.append(reminder)
        logger.info("Reminder created: %s (priority=%s)", title, priority)

        return {
            "message": f"Reminder created: '{title}'",
            "reminder": reminder,
            "total_reminders": len(_reminders),
        }

    def handle_create_schedule(
        self,
        name: str = "",
        cron_expression: str = "",
        action: str = "",
        description: str = "",
        enabled: bool = True,
        **kw: Any,
    ) -> dict[str, Any]:

        if not name:
            raise ValueError("A schedule 'name' is required")

        schedule_id = str(uuid.uuid4())[:8]
        schedule = {
            "id": schedule_id,
            "name": name,
            "cron_expression": cron_expression or "0 * * * *",
            "action": action,
            "description": description or f"Scheduled: {name}",
            "enabled": enabled,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "next_run": self._parse_cron_next(cron_expression or "0 * * * *"),
            "run_count": 0,
        }

        _schedules[schedule_id] = schedule
        logger.info("Schedule created: %s (%s)", name, cron_expression)

        return {
            "message": f"Schedule '{name}' created",
            "schedule": schedule,
            "total_schedules": len(_schedules),
        }

    def handle_track_deadline(
        self,
        title: str = "",
        due_date: str = "",
        assignee: str = "",
        project: str = "",
        priority: str = "medium",
        milestones: list[dict[str, str]] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        if not title or not due_date:
            raise ValueError("Both 'title' and 'due_date' are required")

        deadline = {
            "id": str(uuid.uuid4())[:8],
            "title": title,
            "due_date": due_date,
            "assignee": assignee,
            "project": project,
            "priority": priority,
            "status": "on_track",
            "milestones": milestones or [],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "days_remaining": self._days_until(due_date),
        }

        days = deadline["days_remaining"]
        if days is not None:
            if days < 0:
                deadline["status"] = "overdue"
            elif days <= 3:
                deadline["status"] = "at_risk"
            elif days <= 7:
                deadline["status"] = "approaching"

        _deadlines.append(deadline)

        return {
            "message": f"Deadline tracked: '{title}' due {due_date}",
            "deadline": deadline,
            "total_deadlines": len(_deadlines),
        }

    def handle_estimate_time(
        self,
        tasks: list[dict[str, Any]] | None = None,
        methodology: str = "three_point",
        **kw: Any,
    ) -> dict[str, Any]:

        tasks = tasks or []
        estimates: list[dict[str, Any]] = []
        total_hours = 0.0

        for task in tasks:
            title = task.get("title", "Unnamed")

            if methodology == "three_point":
                o = task.get("optimistic_hours", 1)
                m = task.get("likely_hours", 2)
                p = task.get("pessimistic_hours", 4)

                pert = (o + 4 * m + p) / 6
                std_dev = (p - o) / 6
                estimates.append({
                    "task": title,
                    "estimate_hours": round(pert, 1),
                    "std_dev": round(std_dev, 1),
                    "range": f"{round(pert - std_dev, 1)} - {round(pert + std_dev, 1)} hours",
                    "confidence": "68%",
                })
                total_hours += pert

            elif methodology == "t_shirt":
                complexity = task.get("complexity", "medium")
                hours_map = {"low": 2, "medium": 5, "high": 13, "critical": 21}
                hours = hours_map.get(complexity, 5)
                estimates.append({"task": title, "complexity": complexity, "estimate_hours": hours})
                total_hours += hours

            elif methodology == "fibonacci":
                complexity = task.get("complexity", "medium")
                fib_map = {"low": 1, "medium": 3, "high": 8, "critical": 13}
                points = fib_map.get(complexity, 3)
                hours = points * 2
                estimates.append({"task": title, "story_points": points, "estimate_hours": hours})
                total_hours += hours

        buffer_pct = 20
        total_with_buffer = total_hours * (1 + buffer_pct / 100)

        return {
            "message": f"Estimated {len(tasks)} tasks: {total_hours:.1f}h (+ {buffer_pct}% buffer = {total_with_buffer:.1f}h)",
            "methodology": methodology,
            "estimates": estimates,
            "total_hours": round(total_hours, 1),
            "buffer_percent": buffer_pct,
            "total_with_buffer": round(total_with_buffer, 1),
            "total_days": round(total_with_buffer / 8, 1),
        }

    def handle_list_upcoming(
        self,
        days_ahead: int = 7,
        **kw: Any,
    ) -> dict[str, Any]:

        upcoming_reminders = [
            r for r in _reminders if r["status"] == "pending"
        ]

        upcoming_deadlines = sorted(
            [d for d in _deadlines if d["status"] != "completed"],
            key=lambda d: d.get("due_date", ""),
        )

        active_schedules = [
            {"name": s["name"], "cron": s["cron_expression"], "next_run": s["next_run"]}
            for s in _schedules.values() if s["enabled"]
        ]

        return {
            "message": f"Upcoming in next {days_ahead} days",
            "reminders": upcoming_reminders[:10],
            "deadlines": [
                {"title": d["title"], "due": d["due_date"], "status": d["status"], "days_left": d.get("days_remaining")}
                for d in upcoming_deadlines[:10]
            ],
            "schedules": active_schedules[:10],
            "total_items": len(upcoming_reminders) + len(upcoming_deadlines) + len(active_schedules),
        }

    def _parse_cron_next(self, expr: str) -> str:

        return f"(next run calculated from: {expr})"

    def _days_until(self, date_str: str) -> int | None:

        try:
            from datetime import datetime
            target = datetime.strptime(date_str, "%Y-%m-%d")
            now = datetime.now()
            return (target - now).days
        except Exception:
            return None
