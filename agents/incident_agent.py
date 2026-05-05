from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.incident")

_incidents: dict[str, dict[str, Any]] = {}
_runbooks: dict[str, dict[str, Any]] = {}


class IncidentAgent(BaseAgent):

    agent_name = "incident_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "incident_management",
            "status": "ready",
            "active_incidents": len([i for i in _incidents.values() if i["status"] in ("open", "investigating")]),
            "total_incidents": len(_incidents),
            "runbooks": len(_runbooks),
            "capabilities": [
                "create_incident", "update_incident", "create_postmortem",
                "create_runbook", "escalate",
            ],
        }

    def handle_create_incident(
        self,
        title: str = "",
        severity: str = "P2",
        description: str = "",
        affected_service: str = "",
        reporter: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        if not title:
            raise ValueError("An incident 'title' is required")

        incident_id = f"INC-{str(uuid.uuid4())[:6].upper()}"
        incident = {
            "id": incident_id,
            "title": title,
            "severity": severity.upper(),
            "description": description,
            "affected_service": affected_service,
            "reporter": reporter or "system",
            "status": "open",
            "timeline": [
                {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": "Incident created"}
            ],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "resolved_at": None,
            "assignee": None,
        }
        _incidents[incident_id] = incident
        logger.info("Incident created: %s [%s] - %s", incident_id, severity, title)

        return {
            "message": f"Incident {incident_id} created: {title} [{severity}]",
            "incident": incident,
            "recommended_actions": self._get_severity_playbook(severity),
        }

    def handle_update_incident(
        self,
        incident_id: str = "",
        status: str = "",
        update: str = "",
        assignee: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        if not incident_id:
            raise ValueError("'incident_id' is required")

        incident = _incidents.get(incident_id)
        if not incident:
            return {"message": f"Incident {incident_id} not found", "known_incidents": list(_incidents.keys())}

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if status:
            incident["status"] = status
            incident["timeline"].append({"time": now, "event": f"Status changed to {status}"})
        if update:
            incident["timeline"].append({"time": now, "event": update})
        if assignee:
            incident["assignee"] = assignee
            incident["timeline"].append({"time": now, "event": f"Assigned to {assignee}"})
        if status == "resolved":
            incident["resolved_at"] = now

        return {
            "message": f"Incident {incident_id} updated",
            "incident": incident,
        }

    def handle_create_postmortem(
        self,
        incident_id: str = "",
        root_cause: str = "",
        impact: str = "",
        lessons_learned: list[str] | None = None,
        action_items: list[dict[str, str]] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:
        if not incident_id:
            raise ValueError("'incident_id' is required")

        incident = _incidents.get(incident_id, {})
        lessons = lessons_learned or []
        actions = action_items or []

        postmortem = f"# Post-Mortem: {incident.get('title', incident_id)}\n\n"
        postmortem += f"**Incident ID:** {incident_id}\n"
        postmortem += f"**Severity:** {incident.get('severity', 'Unknown')}\n"
        postmortem += f"**Status:** {incident.get('status', 'Unknown')}\n\n"
        postmortem += f"## Root Cause\n{root_cause or 'To be determined'}\n\n"
        postmortem += f"## Impact\n{impact or 'To be assessed'}\n\n"

        if lessons:
            postmortem += "## Lessons Learned\n"
            for lesson in lessons:
                postmortem += f"- {lesson}\n"
            postmortem += "\n"

        if actions:
            postmortem += "## Action Items\n"
            for item in actions:
                postmortem += f"- [ ] **{item.get('owner', 'TBD')}**: {item.get('task', '')} (Due: {item.get('due', 'TBD')})\n"

        return {
            "message": f"Post-mortem generated for {incident_id}",
            "postmortem": postmortem,
            "action_item_count": len(actions),
        }

    def handle_create_runbook(
        self,
        name: str = "",
        trigger: str = "",
        steps: list[str] | None = None,
        escalation_path: list[str] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:
        if not name:
            raise ValueError("A runbook 'name' is required")

        runbook_id = str(uuid.uuid4())[:8]
        steps = steps or ["Acknowledge alert", "Check monitoring dashboards", "Identify root cause", "Apply fix", "Verify resolution"]
        escalation = escalation_path or ["On-call engineer", "Team lead", "Engineering manager", "VP Engineering"]

        runbook = {
            "id": runbook_id,
            "name": name,
            "trigger": trigger,
            "steps": [{"order": i + 1, "action": s, "completed": False} for i, s in enumerate(steps)],
            "escalation_path": escalation,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _runbooks[runbook_id] = runbook

        return {
            "message": f"Runbook '{name}' created with {len(steps)} steps",
            "runbook": runbook,
        }

    def handle_escalate(
        self,
        incident_id: str = "",
        reason: str = "",
        escalate_to: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        if not incident_id:
            raise ValueError("'incident_id' is required")

        incident = _incidents.get(incident_id)
        if not incident:
            return {"message": f"Incident {incident_id} not found"}

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        incident["timeline"].append({
            "time": now,
            "event": f"ESCALATED to {escalate_to or 'next level'}: {reason}",
        })
        incident["status"] = "escalated"

        return {
            "message": f"Incident {incident_id} escalated to {escalate_to or 'next level'}",
            "incident": incident,
            "reason": reason,
        }

    def _get_severity_playbook(self, severity: str) -> list[str]:
        playbooks = {
            "P1": ["Page on-call immediately", "Open war room", "Notify stakeholders within 15 min", "Post updates every 30 min"],
            "P2": ["Notify on-call", "Begin investigation within 30 min", "Post updates every 1 hour"],
            "P3": ["Create ticket", "Investigate during business hours", "Update within 24 hours"],
            "P4": ["Log for tracking", "Address in next sprint"],
        }
        return playbooks.get(severity.upper(), playbooks["P3"])
