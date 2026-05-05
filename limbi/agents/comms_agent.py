

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from . import BaseAgent

logger = logging.getLogger("limbi.agents.comms")

class CommsAgent(BaseAgent):

    agent_name = "comms_agent"

    def __init__(self) -> None:
        self._slack_webhook = os.getenv("SLACK_WEBHOOK_URL", "")
        self._smtp_configured = bool(os.getenv("SMTP_HOST"))
        self._notification_log: list[dict[str, Any]] = []

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "communication",
            "status": "ready",
            "slack_configured": bool(self._slack_webhook),
            "smtp_configured": self._smtp_configured,
            "notifications_sent": len(self._notification_log),
        }

    def handle_draft_email(
        self,
        to: str = "",
        subject: str = "",
        body: str = "",
        tone: str = "professional",
        cc: str = "",
        include_signature: bool = True,
        **kw: Any,
    ) -> dict[str, Any]:

        if not to or not subject:
            raise ValueError("Both 'to' and 'subject' are required")

        greeting = self._get_greeting(to, tone)
        closing = self._get_closing(tone)
        signature = self._get_signature() if include_signature else ""

        email_body = (
            f"{greeting}\n\n"
            f"{body}\n\n"
            f"{closing}\n"
            f"{signature}"
        )

        email = {
            "to": to,
            "cc": cc,
            "subject": subject,
            "body": email_body,
            "tone": tone,
        }

        return {
            "message": f"Email drafted: '{subject}' -> {to}",
            "email": email,
            "word_count": len(email_body.split()),
            "ready_to_send": self._smtp_configured,
        }

    def handle_send_slack(
        self,
        channel: str = "#general",
        message: str = "",
        username: str = "StepWise AI",
        emoji: str = ":robot_face:",
        blocks: list[dict[str, Any]] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        if not message and not blocks:
            raise ValueError("Either 'message' or 'blocks' is required")

        payload: dict[str, Any] = {
            "channel": channel,
            "username": username,
            "icon_emoji": emoji,
        }

        if blocks:
            payload["blocks"] = blocks
        else:
            payload["text"] = message

        if self._slack_webhook:
            try:
                import httpx

                with httpx.Client(timeout=10) as client:
                    resp = client.post(self._slack_webhook, json=payload)
                    return {
                        "message": f"Slack message sent to {channel}",
                        "channel": channel,
                        "status_code": resp.status_code,
                        "delivered": resp.status_code == 200,
                    }
            except Exception as exc:
                return {
                    "message": f"Slack send failed: {exc}",
                    "channel": channel,
                    "delivered": False,
                    "error": str(exc),
                }

        return {
            "message": f"[SIMULATED] Slack message sent to {channel}",
            "channel": channel,
            "text": message or "[Block Kit message]",
            "delivered": False,
            "note": "Configure SLACK_WEBHOOK_URL for live delivery",
        }

    def handle_draft_meeting_notes(
        self,
        title: str = "",
        attendees: list[str] | None = None,
        discussion_points: list[str] | None = None,
        decisions: list[str] | None = None,
        action_items: list[dict[str, str]] | None = None,
        duration_min: int = 30,
        **kw: Any,
    ) -> dict[str, Any]:

        if not title:
            raise ValueError("A meeting 'title' is required")

        attendees = attendees or ["(attendees not specified)"]
        discussion_points = discussion_points or []
        decisions = decisions or []
        action_items = action_items or []

        date = time.strftime("%Y-%m-%d %H:%M", time.localtime())

        notes = f"# Meeting Notes: {title}\n\n"
        notes += f"**Date:** {date}\n"
        notes += f"**Duration:** {duration_min} minutes\n"
        notes += f"**Attendees:** {', '.join(attendees)}\n\n"

        if discussion_points:
            notes += "## Discussion Points\n"
            for i, point in enumerate(discussion_points, 1):
                notes += f"{i}. {point}\n"
            notes += "\n"

        if decisions:
            notes += "## Decisions Made\n"
            for d in decisions:
                notes += f" {d}\n"
            notes += "\n"

        if action_items:
            notes += "## Action Items\n"
            for item in action_items:
                owner = item.get("owner", "TBD")
                task = item.get("task", "")
                due = item.get("due", "TBD")
                notes += f"- [ ] **{owner}**: {task} (Due: {due})\n"

        return {
            "message": f"Meeting notes drafted for '{title}'",
            "notes": notes,
            "word_count": len(notes.split()),
            "action_item_count": len(action_items),
        }

    def handle_create_notification(
        self,
        title: str = "",
        body: str = "",
        severity: str = "info",
        channel: str = "system",
        **kw: Any,
    ) -> dict[str, Any]:

        if not title:
            raise ValueError("A notification 'title' is required")

        notification = {
            "id": len(self._notification_log) + 1,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "title": title,
            "body": body,
            "severity": severity,
            "channel": channel,
            "read": False,
        }

        self._notification_log.append(notification)
        logger.info("Notification created: [%s] %s", severity, title)

        return {
            "message": f"Notification created: [{severity.upper()}] {title}",
            "notification": notification,
            "total_notifications": len(self._notification_log),
        }

    def handle_draft_announcement(
        self,
        title: str = "",
        body: str = "",
        audience: str = "team",
        urgency: str = "normal",
        channels: list[str] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        if not title or not body:
            raise ValueError("Both 'title' and 'body' are required")

        channels = channels or ["email", "slack"]
        emoji_map = {"low": "", "normal": "", "high": "", "critical": ""}
        emoji = emoji_map.get(urgency, "")

        announcement = (
            f"{emoji} **{title}**\n\n"
            f"{body}\n\n"
            f"---\n"
            f"*Audience: {audience} | Urgency: {urgency} | "
            f"Channels: {', '.join(channels)}*"
        )

        return {
            "message": f"Announcement drafted for {audience}",
            "announcement": announcement,
            "title": title,
            "audience": audience,
            "channels": channels,
            "urgency": urgency,
        }

    def _get_greeting(self, recipient: str, tone: str) -> str:
        name = recipient.split("@")[0].replace(".", " ").title() if "@" in recipient else recipient
        greetings = {
            "professional": f"Dear {name},",
            "casual": f"Hey {name},",
            "urgent": f"Hi {name} - this is urgent.",
            "formal": f"Dear {name},",
            "friendly": f"Hi {name}! ",
        }
        return greetings.get(tone, f"Hello {name},")

    def _get_closing(self, tone: str) -> str:
        closings = {
            "professional": "Best regards,",
            "casual": "Cheers,",
            "urgent": "Please respond ASAP.\n\nBest,",
            "formal": "Sincerely,",
            "friendly": "Talk soon! ",
        }
        return closings.get(tone, "Best,")

    def _get_signature(self) -> str:
        name = os.getenv("USER_NAME", "StepWise AI")
        role = os.getenv("USER_ROLE", "AI Assistant")
        return f"\n{name}\n{role}"
