

from __future__ import annotations

import re
from typing import Any

from agents import BaseAgent

class LegalAgent(BaseAgent):

    agent_name = "legal_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "legal",
            "status": "ready",
            "capabilities": [
                "summarize_clause",
                "flag_contract_risks",
                "generate_nda_checklist",
                "classify_legal_request",
                "draft_policy_notice",
            ],
        }

    def handle_summarize_clause(self, clause: str = "", **kw: Any) -> dict[str, Any]:
        if not clause:
            raise ValueError("'clause' is required")
        sentences = [part.strip() for part in re.split(r"[.;]", clause) if part.strip()]
        return {"message": "Summarized clause", "summary": sentences[:3]}

    def handle_flag_contract_risks(self, contract_text: str = "", **kw: Any) -> dict[str, Any]:
        if not contract_text:
            raise ValueError("'contract_text' is required")
        text = contract_text.lower()
        risks = []
        if "unlimited liability" in text:
            risks.append("unlimited_liability")
        if "perpetual" in text and "termination" not in text:
            risks.append("perpetual_term_without_exit")
        if "exclusive" in text:
            risks.append("exclusivity")
        return {"message": "Flagged contract risks", "risks": risks}

    def handle_generate_nda_checklist(self, mutual: bool = True, **kw: Any) -> dict[str, Any]:
        checklist = ["define confidential information", "specify permitted use", "set duration", "include return or deletion obligations"]
        if mutual:
            checklist.append("confirm obligations apply bilaterally")
        return {"message": "Generated NDA checklist", "checklist": checklist}

    def handle_classify_legal_request(self, request: str = "", **kw: Any) -> dict[str, Any]:
        if not request:
            raise ValueError("'request' is required")
        text = request.lower()
        category = "general"
        if "contract" in text or "msa" in text:
            category = "commercial"
        elif "privacy" in text or "gdpr" in text:
            category = "privacy"
        elif "employment" in text:
            category = "employment"
        return {"message": "Classified legal request", "category": category}

    def handle_draft_policy_notice(self, topic: str = "", audience: str = "employees", **kw: Any) -> dict[str, Any]:
        if not topic:
            raise ValueError("'topic' is required")
        notice = f"This notice informs {audience} about the updated policy on {topic}. Please review the changes and follow the documented requirements."
        return {"message": "Drafted policy notice", "notice": notice}
