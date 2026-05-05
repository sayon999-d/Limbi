from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.reporting")

_reports: list[dict[str, Any]] = []


class ReportingAgent(BaseAgent):

    agent_name = "reporting_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "reporting", "status": "ready", "reports_generated": len(_reports), "capabilities": ["generate_report", "executive_summary", "sprint_report", "status_update", "changelog"]}

    def handle_generate_report(self, title: str = "", sections: list[dict[str, str]] | None = None, format: str = "markdown", **kw: Any) -> dict[str, Any]:
        if not title:
            raise ValueError("A report 'title' is required")
        sections = sections or [{"heading": "Summary", "content": "..."}, {"heading": "Details", "content": "..."}, {"heading": "Next Steps", "content": "..."}]
        report = f"# {title}\n\n**Generated:** {time.strftime('%Y-%m-%d %H:%M', time.gmtime())}\n\n"
        for s in sections:
            report += f"## {s.get('heading', 'Section')}\n{s.get('content', '')}\n\n"
        _reports.append({"title": title, "format": format, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        return {"message": f"Report generated: '{title}'", "report": report, "format": format, "word_count": len(report.split())}

    def handle_executive_summary(self, project: str = "", highlights: list[str] | None = None, risks: list[str] | None = None, metrics: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        highlights = highlights or []
        risks = risks or []
        summary = f"# Executive Summary: {project or 'Project Update'}\n\n"
        summary += f"**Date:** {time.strftime('%Y-%m-%d')}\n\n"
        if highlights:
            summary += "## Highlights\n" + "\n".join(f"- {h}" for h in highlights) + "\n\n"
        if risks:
            summary += "## Risks & Blockers\n" + "\n".join(f"- {r}" for r in risks) + "\n\n"
        if metrics:
            summary += "## Key Metrics\n" + "\n".join(f"- {k}: {v}" for k, v in metrics.items()) + "\n"
        return {"message": f"Executive summary for '{project or 'project'}'", "summary": summary}

    def handle_sprint_report(self, sprint_name: str = "", completed: list[str] | None = None, in_progress: list[str] | None = None, blocked: list[str] | None = None, velocity: int = 0, **kw: Any) -> dict[str, Any]:
        completed = completed or []
        in_progress = in_progress or []
        blocked = blocked or []
        report = f"# Sprint Report: {sprint_name or 'Current Sprint'}\n\n"
        report += f"**Velocity:** {velocity} points\n\n"
        report += f"## Completed ({len(completed)})\n" + "\n".join(f"- {t}" for t in completed) + "\n\n"
        report += f"## In Progress ({len(in_progress)})\n" + "\n".join(f"- {t}" for t in in_progress) + "\n\n"
        report += f"## Blocked ({len(blocked)})\n" + "\n".join(f"- {t}" for t in blocked) + "\n"
        return {"message": f"Sprint report: {len(completed)} done, {len(in_progress)} in progress, {len(blocked)} blocked", "report": report, "velocity": velocity}

    def handle_status_update(self, project: str = "", status: str = "on_track", summary: str = "", **kw: Any) -> dict[str, Any]:
        emoji = {"on_track": "", "at_risk": "", "off_track": "", "completed": ""}.get(status, "")
        update = f"{emoji} **{project or 'Project'}** — {status.replace('_', ' ').title()}\n\n{summary}"
        return {"message": f"Status update: {project or 'project'} is {status}", "update": update, "status": status}

    def handle_changelog(self, version: str = "", changes: list[dict[str, str]] | None = None, **kw: Any) -> dict[str, Any]:
        if not version:
            raise ValueError("'version' is required")
        changes = changes or []
        type_emoji = {"added": "", "changed": "", "fixed": "", "removed": "", "security": "", "deprecated": ""}
        changelog = f"# Changelog — v{version}\n\nDate: {time.strftime('%Y-%m-%d')}\n\n"
        grouped: dict[str, list[str]] = {}
        for c in changes:
            t = c.get("type", "changed")
            grouped.setdefault(t, []).append(c.get("description", ""))
        for t, items in grouped.items():
            emoji = type_emoji.get(t, "")
            changelog += f"## {emoji} {t.title()}\n" + "\n".join(f"- {i}" for i in items) + "\n\n"
        return {"message": f"Changelog for v{version}: {len(changes)} entries", "changelog": changelog, "version": version}
