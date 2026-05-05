

from __future__ import annotations

from typing import Any

from agents import BaseAgent

class RecruitingAgent(BaseAgent):

    agent_name = "recruiting_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "recruiting", "status": "ready", "capabilities": ["score_candidate", "draft_outreach", "interview_plan", "debrief_summary"]}

    def handle_score_candidate(self, skills_match: int = 0, experience_years: int = 0, urgency_fit: str = "medium", **kw: Any) -> dict[str, Any]:
        score = min(100, skills_match + min(experience_years * 5, 30) + (15 if urgency_fit == "high" else 5))
        return {"message": "Scored candidate", "score": score, "recommendation": "advance" if score >= 70 else "review"}

    def handle_draft_outreach(self, candidate_name: str = "", role: str = "", company: str = "", **kw: Any) -> dict[str, Any]:
        if not role or not company:
            raise ValueError("'role' and 'company' are required")
        text = f"Hi {candidate_name or 'there'}, wed love to discuss the {role} opportunity at {company}. Let us know if you're open to a short intro."
        return {"message": "Drafted recruiting outreach", "outreach": text}

    def handle_interview_plan(self, role: str = "", stages: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        if not role:
            raise ValueError("'role' is required")
        return {"message": f"Created interview plan for {role}", "stages": stages or ["screen", "technical", "panel", "final"]}

    def handle_debrief_summary(self, notes: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        notes = notes or []
        return {"message": "Summarized interview debrief", "summary": " ".join(notes)[:500], "note_count": len(notes)}
