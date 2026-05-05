from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.notification")

_notification_channels: dict[str, dict[str, Any]] = {}
_notification_history: list[dict[str, Any]] = []


class NotificationAgent(BaseAgent):

    agent_name = "notification_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "notification", "status": "ready", "channels": len(_notification_channels), "sent": len(_notification_history), "capabilities": ["send_push", "send_sms", "send_webhook", "create_alert_rule", "list_notifications"]}

    def handle_send_push(self, title: str = "", body: str = "", targets: list[str] | None = None, priority: str = "normal", **kw: Any) -> dict[str, Any]:
        if not title:
            raise ValueError("'title' is required")
        targets = targets or ["all_users"]
        notif = {"id": str(uuid.uuid4())[:8], "type": "push", "title": title, "body": body, "targets": targets, "priority": priority, "sent_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        _notification_history.append(notif)
        return {"message": f"[SIMULATED] Push notification sent: '{title}' to {len(targets)} targets", "notification": notif}

    def handle_send_sms(self, to: str = "", message: str = "", **kw: Any) -> dict[str, Any]:
        if not to or not message:
            raise ValueError("Both 'to' and 'message' are required")
        notif = {"id": str(uuid.uuid4())[:8], "type": "sms", "to": to, "message": message[:160], "sent_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        _notification_history.append(notif)
        return {"message": f"[SIMULATED] SMS sent to {to}", "notification": notif, "chars": len(message[:160])}

    def handle_send_webhook(self, url: str = "", payload: dict | None = None, method: str = "POST", **kw: Any) -> dict[str, Any]:
        if not url:
            raise ValueError("'url' is required")
        return {"message": f"[SIMULATED] Webhook {method} to {url}", "url": url, "method": method, "payload": payload, "status_code": 200}

    def handle_create_alert_rule(self, name: str = "", condition: str = "", channels: list[str] | None = None, severity: str = "warning", **kw: Any) -> dict[str, Any]:
        if not name or not condition:
            raise ValueError("Both 'name' and 'condition' are required")
        channels = channels or ["email", "slack"]
        rule = {"id": str(uuid.uuid4())[:8], "name": name, "condition": condition, "channels": channels, "severity": severity, "enabled": True, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        return {"message": f"Alert rule '{name}' created", "rule": rule}

    def handle_list_notifications(self, limit: int = 20, **kw: Any) -> dict[str, Any]:
        recent = _notification_history[-limit:]
        return {"message": f"Showing {len(recent)} of {len(_notification_history)} notifications", "notifications": recent, "total": len(_notification_history)}
