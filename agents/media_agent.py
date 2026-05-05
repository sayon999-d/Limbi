

from __future__ import annotations

from typing import Any

from agents import BaseAgent

class MediaAgent(BaseAgent):

    agent_name = "media_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "media", "status": "ready", "capabilities": ["editorial_brief", "production_schedule", "audience_breakdown", "distribution_plan"]}

    def handle_editorial_brief(self, story: str = "", angle: str = "", **kw: Any) -> dict[str, Any]:
        if not story:
            raise ValueError("'story' is required")
        return {"message": "Created editorial brief", "story": story, "angle": angle or "informative", "sections": ["hook", "context", "evidence", "close"]}

    def handle_production_schedule(self, content_type: str = "", days: int = 7, **kw: Any) -> dict[str, Any]:
        return {"message": "Created production schedule", "content_type": content_type, "days": days}

    def handle_audience_breakdown(self, channels: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        channels = channels or []
        return {"message": "Prepared audience breakdown", "channels": [{"channel": channel, "priority": "high" if idx == 0 else "medium"} for idx, channel in enumerate(channels)]}

    def handle_distribution_plan(self, asset: str = "", **kw: Any) -> dict[str, Any]:
        return {"message": "Created distribution plan", "asset": asset, "stages": ["owned channels", "partner channels", "repurposing", "performance review"]}
