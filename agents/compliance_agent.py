from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.compliance")

_audit_trails: list[dict[str, Any]] = []


class ComplianceAgent(BaseAgent):

    agent_name = "compliance_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "compliance",
            "status": "ready",
            "capabilities": [
                "gdpr_check", "hipaa_check", "soc2_review",
                "data_classification", "generate_audit_trail",
            ],
        }

    def handle_gdpr_check(
        self,
        data_types: list[str] | None = None,
        has_consent_mechanism: bool = False,
        has_dpo: bool = False,
        stores_eu_data: bool = True,
        **kw: Any,
    ) -> dict[str, Any]:
        data_types = data_types or []
        findings: list[dict[str, Any]] = []
        pii_types = {"email", "name", "address", "phone", "ip_address", "dob", "ssn", "biometric"}
        detected_pii = [d for d in data_types if d.lower() in pii_types]

        if detected_pii and not has_consent_mechanism:
            findings.append({"severity": "critical", "finding": "PII collected without explicit consent mechanism", "article": "Art. 6 & 7"})
        if stores_eu_data and not has_dpo:
            findings.append({"severity": "high", "finding": "No Data Protection Officer designated", "article": "Art. 37"})
        if detected_pii:
            findings.append({"severity": "medium", "finding": f"PII types detected: {', '.join(detected_pii)} — ensure data minimization", "article": "Art. 5(1)(c)"})
        if not findings:
            findings.append({"severity": "info", "finding": "No obvious GDPR gaps detected", "article": "N/A"})

        return {
            "message": f"GDPR compliance review: {len(findings)} findings",
            "framework": "GDPR",
            "pii_detected": detected_pii,
            "findings": findings,
            "risk_level": "critical" if any(f["severity"] == "critical" for f in findings) else "medium",
        }

    def handle_hipaa_check(
        self,
        has_phi: bool = False,
        encryption_at_rest: bool = False,
        encryption_in_transit: bool = False,
        access_controls: bool = False,
        audit_logging: bool = False,
        **kw: Any,
    ) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        if has_phi and not encryption_at_rest:
            findings.append({"severity": "critical", "finding": "PHI stored without encryption at rest", "rule": "§164.312(a)(2)(iv)"})
        if has_phi and not encryption_in_transit:
            findings.append({"severity": "critical", "finding": "PHI transmitted without encryption", "rule": "§164.312(e)(1)"})
        if not access_controls:
            findings.append({"severity": "high", "finding": "Missing access controls for PHI", "rule": "§164.312(a)(1)"})
        if not audit_logging:
            findings.append({"severity": "high", "finding": "No audit logging for PHI access", "rule": "§164.312(b)"})
        if not findings:
            findings.append({"severity": "info", "finding": "Basic HIPAA safeguards appear in place"})

        return {
            "message": f"HIPAA compliance review: {len(findings)} findings",
            "framework": "HIPAA",
            "has_phi": has_phi,
            "findings": findings,
            "risk_level": "critical" if any(f["severity"] == "critical" for f in findings) else "low",
        }

    def handle_soc2_review(
        self,
        trust_principles: list[str] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:
        principles = trust_principles or ["security", "availability", "confidentiality"]
        checklist_map = {
            "security": ["Firewall & network controls", "Encryption standards", "Vulnerability management", "Incident response plan"],
            "availability": ["SLA definitions", "Disaster recovery plan", "Monitoring & alerting", "Capacity planning"],
            "confidentiality": ["Data classification policy", "Access controls", "NDA processes", "Data retention policy"],
            "processing_integrity": ["Input validation", "Output reconciliation", "Error handling", "Change management"],
            "privacy": ["Privacy notice", "Consent management", "Data subject rights", "Third-party data sharing"],
        }
        review = {}
        for p in principles:
            items = checklist_map.get(p, [f"Review {p} controls"])
            review[p] = [{"item": item, "status": "needs_review"} for item in items]

        return {
            "message": f"SOC 2 review covering {len(principles)} trust principles",
            "framework": "SOC 2 Type II",
            "principles_reviewed": principles,
            "checklist": review,
            "total_controls": sum(len(v) for v in review.values()),
        }

    def handle_data_classification(
        self,
        data_fields: list[str] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:
        data_fields = data_fields or []
        sensitive_keywords = {"ssn", "password", "credit_card", "dob", "salary", "health", "biometric", "secret"}
        pii_keywords = {"email", "name", "phone", "address", "ip_address", "location"}
        internal_keywords = {"employee_id", "department", "project", "revenue", "cost"}

        classified: list[dict[str, str]] = []
        for field in data_fields:
            lower = field.lower()
            if any(k in lower for k in sensitive_keywords):
                level = "restricted"
            elif any(k in lower for k in pii_keywords):
                level = "confidential"
            elif any(k in lower for k in internal_keywords):
                level = "internal"
            else:
                level = "public"
            classified.append({"field": field, "classification": level})

        return {
            "message": f"Classified {len(data_fields)} data fields",
            "classifications": classified,
            "summary": {
                level: len([c for c in classified if c["classification"] == level])
                for level in ["restricted", "confidential", "internal", "public"]
            },
        }

    def handle_generate_audit_trail(
        self,
        action: str = "",
        actor: str = "",
        resource: str = "",
        details: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        if not action:
            raise ValueError("An 'action' description is required")

        entry = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action": action,
            "actor": actor or "system",
            "resource": resource,
            "details": details,
            "integrity_hash": None,
        }
        import hashlib
        entry["integrity_hash"] = hashlib.sha256(
            f"{entry['timestamp']}:{entry['action']}:{entry['actor']}:{entry['resource']}".encode()
        ).hexdigest()[:16]
        _audit_trails.append(entry)

        return {
            "message": f"Audit trail entry recorded: {action}",
            "entry": entry,
            "total_entries": len(_audit_trails),
        }
