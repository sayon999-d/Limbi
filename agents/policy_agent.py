

from __future__ import annotations

from typing import Any

from agents import BaseAgent

class PolicyAgent(BaseAgent):

    agent_name = "policy_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "policy",
            "status": "ready",
            "capabilities": [
                "evaluate_action_policy",
                "classify_data",
                "generate_compliance_checklist",
                "summarize_policy",
                "detect_policy_conflicts",
            ],
        }

    def handle_evaluate_action_policy(self, action: str = "", data_classification: str = "internal", **kw: Any) -> dict[str, Any]:
        if not action:
            raise ValueError("'action' is required")
        risk = "low"
        if data_classification in {"confidential", "restricted"}:
            risk = "high"
        elif "prod" in action.lower() or "delete" in action.lower():
            risk = "medium"
        return {"message": "Evaluated action against policy", "action": action, "risk": risk}

    def handle_classify_data(self, description: str = "", **kw: Any) -> dict[str, Any]:
        if not description:
            raise ValueError("'description' is required")
        text = description.lower()
        if any(token in text for token in ["ssn", "passport", "medical", "credit card"]):
            classification = "restricted"
        elif any(token in text for token in ["customer", "employee", "personal"]):
            classification = "confidential"
        elif any(token in text for token in ["pricing", "roadmap", "strategy"]):
            classification = "internal"
        else:
            classification = "public"
        return {"message": "Classified data", "classification": classification}

    def handle_generate_compliance_checklist(self, framework: str = "general", **kw: Any) -> dict[str, Any]:
        items = [
            "document purpose and legal basis",
            "restrict access to least privilege",
            "log access and changes",
            "define retention and deletion policy",
        ]
        if framework.lower() in {"gdpr", "hipaa", "soc2"}:
            items.append(f"map controls to {framework.upper()} requirements")
        return {"message": f"Generated checklist for {framework}", "checklist": items}

    def handle_summarize_policy(self, policy_text: str = "", **kw: Any) -> dict[str, Any]:
        if not policy_text:
            raise ValueError("'policy_text' is required")
        sentences = [part.strip() for part in policy_text.split(".") if part.strip()]
        return {"message": "Summarized policy", "summary": sentences[:5], "sentence_count": len(sentences)}

    def handle_detect_policy_conflicts(self, rules: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        rules = rules or []
        conflicts = []
        normalized = [rule.lower() for rule in rules]
        if any("allow public sharing" in rule for rule in normalized) and any("never share externally" in rule for rule in normalized):
            conflicts.append("sharing_rules_conflict")
        return {"message": "Checked policy conflicts", "conflicts": conflicts, "valid": not conflicts}
