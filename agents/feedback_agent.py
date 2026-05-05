from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.feedback")

_feedback_items: list[dict[str, Any]] = []
_surveys: dict[str, dict[str, Any]] = {}


class FeedbackAgent(BaseAgent):

    agent_name = "feedback_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "feedback", "status": "ready", "feedback_count": len(_feedback_items), "capabilities": ["collect_feedback", "create_survey", "nps_analysis", "feature_request", "sentiment_summary"]}

    def handle_collect_feedback(self, user: str = "", feedback: str = "", category: str = "general", rating: int = 0, **kw: Any) -> dict[str, Any]:
        if not feedback:
            raise ValueError("'feedback' text is required")
        item = {"id": str(uuid.uuid4())[:8], "user": user or "anonymous", "feedback": feedback, "category": category, "rating": rating, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        _feedback_items.append(item)
        return {"message": "Feedback collected", "item": item, "total": len(_feedback_items)}

    def handle_create_survey(self, title: str = "", questions: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        if not title:
            raise ValueError("Survey 'title' is required")
        questions = questions or [{"question": "How satisfied are you?", "type": "rating", "scale": "1-5"}]
        sid = str(uuid.uuid4())[:8]
        survey = {"id": sid, "title": title, "questions": questions, "responses": 0, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        _surveys[sid] = survey
        return {"message": f"Survey '{title}' created with {len(questions)} questions", "survey": survey}

    def handle_nps_analysis(self, scores: list[int] | None = None, **kw: Any) -> dict[str, Any]:
        scores = scores or [9, 10, 8, 7, 6, 10, 9, 8, 5, 10]
        promoters = len([s for s in scores if s >= 9])
        passives = len([s for s in scores if 7 <= s <= 8])
        detractors = len([s for s in scores if s <= 6])
        total = len(scores)
        nps = round((promoters - detractors) / max(total, 1) * 100)
        return {"message": f"NPS Score: {nps}", "nps": nps, "promoters": promoters, "passives": passives, "detractors": detractors, "total_responses": total, "benchmark": "Good" if nps > 50 else "Average" if nps > 0 else "Needs improvement"}

    def handle_feature_request(self, title: str = "", description: str = "", requester: str = "", priority: str = "medium", **kw: Any) -> dict[str, Any]:
        if not title:
            raise ValueError("Feature request 'title' is required")
        return {"message": f"Feature request logged: '{title}'", "request": {"id": str(uuid.uuid4())[:8], "title": title, "description": description, "requester": requester, "priority": priority, "status": "under_review"}}

    def handle_sentiment_summary(self, **kw: Any) -> dict[str, Any]:
        total = len(_feedback_items)
        if not total:
            return {"message": "No feedback collected yet", "total": 0}
        avg_rating = sum(f.get("rating", 0) for f in _feedback_items) / total
        categories = {}
        for f in _feedback_items:
            cat = f.get("category", "general")
            categories[cat] = categories.get(cat, 0) + 1
        return {"message": f"Sentiment summary: {total} feedback items, avg rating {avg_rating:.1f}", "total": total, "average_rating": round(avg_rating, 1), "by_category": categories}
