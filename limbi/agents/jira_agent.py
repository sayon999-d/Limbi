

from __future__ import annotations

import logging
import os
from typing import Any

from . import BaseAgent

logger = logging.getLogger("limbi.agents.jira")

class JiraAgent(BaseAgent):
    agent_name = "jira_agent"

    def __init__(self) -> None:
        self._base_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
        self._email = os.getenv("JIRA_EMAIL", "")
        self._token = os.getenv("JIRA_API_TOKEN", "")
        self._project = os.getenv("JIRA_PROJECT_KEY", "PROJ")

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "status": "ready",
            "jira_configured": bool(self._token and self._base_url),
            "project": self._project,
        }

    def _headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "Content-Type": "application/json"}

    def _auth(self) -> tuple[str, str]:
        return (self._email, self._token)

    def handle_create_ticket(
        self,
        title: str = "",
        description: str = "",
        issue_type: str = "Task",
        priority: str = "Medium",
        assignee: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:

        logger.info("Creating Jira ticket: '%s' [%s / %s]", title, issue_type, priority)

        if self._token and self._base_url:
            import requests

            url = f"{self._base_url}/rest/api/3/issue"
            payload = {
                "fields": {
                    "project": {"key": self._project},
                    "summary": title,
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": description or title}],
                            }
                        ],
                    },
                    "issuetype": {"name": issue_type},
                    "priority": {"name": priority},
                }
            }
            if assignee:
                payload["fields"]["assignee"] = {"accountId": assignee}

            resp = requests.post(
                url,
                headers=self._headers(),
                auth=self._auth(),
                json=payload,
                timeout=15,
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Jira create failed: {resp.text}")
            data = resp.json()
            return {
                "message": f"Ticket {data['key']} created",
                "key": data["key"],
                "url": f"{self._base_url}/browse/{data['key']}",
            }

        return {
            "message": f"[SIMULATED] Jira ticket '{title}' created",
            "key": f"{self._project}-101",
            "title": title,
            "priority": priority,
            "issue_type": issue_type,
            "url": f"https://example.atlassian.net/browse/{self._project}-101",
        }

    def handle_update_ticket(
        self,
        ticket_key: str = "",
        status: str | None = None,
        comment: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:

        logger.info("Updating Jira ticket %s", ticket_key)
        updates: dict[str, Any] = {}
        if status:
            updates["status"] = status
        if comment:
            updates["comment_added"] = comment

        return {
            "message": f"[SIMULATED] Ticket {ticket_key} updated",
            "ticket_key": ticket_key,
            "updates": updates,
        }

    def handle_search_tickets(
        self,
        query: str = "",
        max_results: int = 10,
        **kwargs: Any,
    ) -> dict[str, Any]:

        logger.info("Searching Jira: '%s'", query)

        if self._token and self._base_url:
            import requests

            url = f"{self._base_url}/rest/api/3/search"
            resp = requests.get(
                url,
                headers=self._headers(),
                auth=self._auth(),
                params={"jql": query, "maxResults": max_results},
                timeout=15,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Jira search failed: {resp.text}")
            issues = resp.json().get("issues", [])
            return {
                "results": [
                    {"key": i["key"], "summary": i["fields"]["summary"]}
                    for i in issues
                ],
                "total": resp.json().get("total", 0),
            }

        return {
            "message": f"[SIMULATED] Search results for '{query}'",
            "results": [
                {"key": f"{self._project}-42", "summary": "Example ticket"},
                {"key": f"{self._project}-43", "summary": "Another ticket"},
            ],
            "total": 2,
        }

    def handle_get_ticket(
        self,
        ticket_key: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:

        return {
            "message": f"[SIMULATED] Ticket details for {ticket_key}",
            "key": ticket_key,
            "summary": "Example ticket summary",
            "status": "In Progress",
            "assignee": "developer@example.com",
            "priority": "High",
        }
