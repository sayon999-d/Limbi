from __future__ import annotations

import logging
from typing import Any

from agents.browser_agent import BrowserAgent

logger = logging.getLogger("limbi.agents.web_scraping")


class WebScrapingAgent(BrowserAgent):

    agent_name = "web_scraping_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "web_scraping",
            "status": "ready",
            "capabilities": [
                "fetch_page",
                "extract_links",
                "inspect_forms",
                "summarize_page",
                "check_status",
            ],
        }
