

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Any

from . import BaseAgent

logger = logging.getLogger("limbi.agents.security")

_SECRET_PATTERNS = [
    (r'(?:api[_-]?key|apikey)\s*[=:]\s*["\']?([A-Za-z0-9_\-]{20,})', "API Key"),
    (r'(?:secret|password|passwd|pwd)\s*[=:]\s*["\']?([^\s"\']{8,})', "Password/Secret"),
    (r'ghp_[A-Za-z0-9]{36}', "GitHub Personal Access Token"),
    (r'gho_[A-Za-z0-9]{36}', "GitHub OAuth Token"),
    (r'sk-[A-Za-z0-9]{48}', "OpenAI API Key"),
    (r'sk-ant-[A-Za-z0-9\-]{90,}', "Anthropic API Key"),
    (r'AKIA[A-Z0-9]{16}', "AWS Access Key ID"),
    (r'xox[bporas]-[A-Za-z0-9\-]+', "Slack Token"),
    (r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----', "Private Key"),
    (r'eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+', "JWT Token"),
    (r'(?:bearer|token)\s+[A-Za-z0-9_\-\.]{20,}', "Bearer Token"),
    (r'mongodb(?:\+srv)?://[^\s]+', "MongoDB Connection String"),
    (r'postgres(?:ql)?://[^\s]+', "PostgreSQL Connection String"),
]

class SecurityAgent(BaseAgent):

    agent_name = "security_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "security",
            "status": "ready",
            "secret_patterns": len(_SECRET_PATTERNS),
            "capabilities": [
                "scan_dependencies", "scan_secrets",
                "owasp_check", "lookup_cve", "security_review",
            ],
        }

    def handle_scan_dependencies(
        self,
        requirements: str = "",
        package_json: str = "",
        **kw: Any,
    ) -> dict[str, Any]:

        findings: list[dict[str, Any]] = []
        deps: list[str] = []

        if requirements:
            for line in requirements.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):

                    pkg = re.split(r'[>=<!\[]', line)[0].strip()
                    if pkg:
                        deps.append(pkg)

                        vuln = self._check_known_vulnerable(pkg, line)
                        if vuln:
                            findings.append(vuln)

        if package_json:
            import json
            try:
                pkg = json.loads(package_json)
                for dep_type in ("dependencies", "devDependencies"):
                    for name, version in pkg.get(dep_type, {}).items():
                        deps.append(name)
            except Exception:
                pass

        warnings: list[str] = []
        for line in requirements.strip().split("\n") if requirements else []:
            line = line.strip()
            if line and not line.startswith("#"):
                if ">=" in line and "==" not in line:
                    warnings.append(f"'{line}' uses >= (unpinned) - consider pinning exact version")

        risk = "high" if findings else "medium" if warnings else "low"

        return {
            "message": f"Scanned {len(deps)} dependencies: {len(findings)} vulnerabilities, {len(warnings)} warnings",
            "total_dependencies": len(deps),
            "vulnerabilities": findings,
            "warnings": warnings,
            "risk_level": risk,
            "recommendation": "Fix critical vulnerabilities before deploying" if findings else "Dependencies look clean",
        }

    def handle_scan_secrets(
        self,
        content: str = "",
        filename: str = "unknown",
        **kw: Any,
    ) -> dict[str, Any]:

        if not content:
            raise ValueError("'content' to scan is required")

        findings: list[dict[str, Any]] = []

        for pattern, secret_type in _SECRET_PATTERNS:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:

                line_num = content[:match.start()].count("\n") + 1

                secret_val = match.group()
                masked = secret_val[:8] + "..." + secret_val[-4:] if len(secret_val) > 12 else "****"

                findings.append({
                    "type": secret_type,
                    "line": line_num,
                    "masked_value": masked,
                    "severity": "critical",
                })

        risk = "critical" if findings else "clean"

        return {
            "message": f"{' ' + str(len(findings)) + ' secrets found!' if findings else ' No secrets detected'}",
            "filename": filename,
            "secrets_found": len(findings),
            "findings": findings,
            "risk_level": risk,
            "recommendation": "Rotate all exposed credentials immediately!" if findings else "No secrets detected",
        }

    def handle_owasp_check(
        self,
        app_type: str = "web",
        has_auth: bool = True,
        has_file_upload: bool = False,
        has_user_input: bool = True,
        uses_sql: bool = True,
        **kw: Any,
    ) -> dict[str, Any]:

        checks: list[dict[str, Any]] = [
            {
                "id": "A01", "name": "Broken Access Control",
                "applicable": has_auth,
                "check": "Verify RBAC, path traversal protection, CORS config",
                "severity": "critical",
            },
            {
                "id": "A02", "name": "Cryptographic Failures",
                "applicable": True,
                "check": "Check TLS, password hashing, sensitive data encryption",
                "severity": "critical",
            },
            {
                "id": "A03", "name": "Injection",
                "applicable": has_user_input or uses_sql,
                "check": "SQL injection, XSS, command injection, LDAP injection",
                "severity": "critical",
            },
            {
                "id": "A04", "name": "Insecure Design",
                "applicable": True,
                "check": "Threat modeling, security requirements, secure design patterns",
                "severity": "high",
            },
            {
                "id": "A05", "name": "Security Misconfiguration",
                "applicable": True,
                "check": "Default configs, unnecessary features, error handling",
                "severity": "high",
            },
            {
                "id": "A06", "name": "Vulnerable Components",
                "applicable": True,
                "check": "Outdated dependencies, known CVEs in libraries",
                "severity": "high",
            },
            {
                "id": "A07", "name": "Auth Failures",
                "applicable": has_auth,
                "check": "Brute force protection, session management, MFA",
                "severity": "critical",
            },
            {
                "id": "A08", "name": "Software & Data Integrity",
                "applicable": True,
                "check": "CI/CD pipeline security, deserialization, update verification",
                "severity": "high",
            },
            {
                "id": "A09", "name": "Logging & Monitoring Failures",
                "applicable": True,
                "check": "Audit logging, alerting, incident response",
                "severity": "medium",
            },
            {
                "id": "A10", "name": "SSRF",
                "applicable": has_file_upload or has_user_input,
                "check": "URL validation, internal network protection, allowlists",
                "severity": "high",
            },
        ]

        applicable = [c for c in checks if c["applicable"]]
        critical = [c for c in applicable if c["severity"] == "critical"]

        return {
            "message": f"OWASP Top 10 review: {len(applicable)} applicable checks",
            "app_type": app_type,
            "checks": applicable,
            "total_applicable": len(applicable),
            "critical_count": len(critical),
            "recommendation": "Address all critical items before production deployment",
        }

    def handle_lookup_cve(
        self,
        cve_id: str = "",
        **kw: Any,
    ) -> dict[str, Any]:

        if not cve_id:
            raise ValueError("A 'cve_id' (e.g., CVE-2024-1234) is required")

        if not re.match(r'CVE-\d{4}-\d{4,}', cve_id, re.I):
            return {"message": f"Invalid CVE format: {cve_id}", "valid": False}

        return {
            "message": f"[SIMULATED] CVE lookup for {cve_id}",
            "cve_id": cve_id,
            "status": "simulated",
            "note": "Configure NVD_API_KEY for live CVE lookups",
            "lookup_url": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
        }

    def handle_security_review(
        self,
        project_name: str = "",
        checklist: list[str] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        default_checklist = [
            "Environment variables for secrets (not hardcoded)",
            "Input validation on all user-facing endpoints",
            "Authentication on protected routes",
            "Rate limiting configured",
            "CORS properly restricted",
            "SQL parameterized queries (no string interpolation)",
            "Dependencies pinned and audited",
            "Error messages don't leak internal details",
            "Logging configured without sensitive data",
            "HTTPS enforced in production",
            "File uploads validated and size-limited",
            "CSP headers configured",
        ]

        items = checklist or default_checklist

        return {
            "message": f"Security review checklist for '{project_name or 'Project'}'",
            "project": project_name,
            "checklist": [{"item": item, "status": "needs_review"} for item in items],
            "total_items": len(items),
            "recommendation": "Review each item and mark as pass/fail",
        }

    def _check_known_vulnerable(self, pkg: str, spec: str) -> dict[str, Any] | None:

        known = {
            "pyyaml": {"versions": "<6.0", "cve": "CVE-2020-14343", "severity": "high"},
            "urllib3": {"versions": "<2.0.7", "cve": "CVE-2023-45803", "severity": "medium"},
            "requests": {"versions": "<2.32.0", "cve": "CVE-2024-35195", "severity": "medium"},
            "jinja2": {"versions": "<3.1.3", "cve": "CVE-2024-22195", "severity": "medium"},
        }

        info = known.get(pkg.lower())
        if info:
            return {
                "package": pkg,
                "spec": spec,
                "advisory": f"Versions {info['versions']} have known vulnerability",
                "cve": info["cve"],
                "severity": info["severity"],
                "fix": f"Upgrade {pkg} to latest version",
            }
        return None
