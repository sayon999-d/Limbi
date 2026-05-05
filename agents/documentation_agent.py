from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.documentation")


class DocumentationAgent(BaseAgent):

    agent_name = "documentation_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "documentation", "status": "ready", "capabilities": ["generate_api_docs", "generate_readme", "create_adr", "generate_runbook_doc", "create_glossary"]}

    def handle_generate_api_docs(self, service_name: str = "", endpoints: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        if not service_name:
            raise ValueError("'service_name' is required")
        endpoints = endpoints or [{"method": "GET", "path": "/health", "description": "Health check"}]
        doc = f"# {service_name} API Documentation\n\n"
        doc += f"**Base URL:** `http://localhost:8000`\n**Version:** 1.0.0\n\n"
        for ep in endpoints:
            doc += f"## `{ep.get('method', 'GET')} {ep.get('path', '/')}`\n\n"
            doc += f"{ep.get('description', 'No description')}\n\n"
            if ep.get("params"):
                doc += "**Parameters:**\n" + "\n".join(f"- `{p}`: {desc}" for p, desc in ep["params"].items()) + "\n\n"
        return {"message": f"API docs for {service_name}: {len(endpoints)} endpoints", "documentation": doc}

    def handle_generate_readme(self, project_name: str = "", description: str = "", tech_stack: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        if not project_name:
            raise ValueError("'project_name' is required")
        tech_stack = tech_stack or ["Python", "FastAPI"]
        readme = f"# {project_name}\n\n{description or 'A project.'}\n\n"
        readme += f"## Tech Stack\n" + "\n".join(f"- {t}" for t in tech_stack) + "\n\n"
        readme += "## Getting Started\n\n```bash\npip install -r requirements.txt\nuvicorn main:app --reload\n```\n\n"
        readme += "## Contributing\n\n1. Fork the repo\n2. Create a feature branch\n3. Submit a PR\n\n"
        readme += "## License\n\nMIT\n"
        return {"message": f"README generated for {project_name}", "readme": readme}

    def handle_create_adr(self, title: str = "", context: str = "", decision: str = "", consequences: list[str] | None = None, status: str = "proposed", **kw: Any) -> dict[str, Any]:
        if not title:
            raise ValueError("ADR 'title' is required")
        adr_id = time.strftime("%Y%m%d")
        consequences = consequences or []
        adr = f"# ADR-{adr_id}: {title}\n\n"
        adr += f"**Status:** {status}\n**Date:** {time.strftime('%Y-%m-%d')}\n\n"
        adr += f"## Context\n{context or 'TBD'}\n\n"
        adr += f"## Decision\n{decision or 'TBD'}\n\n"
        if consequences:
            adr += "## Consequences\n" + "\n".join(f"- {c}" for c in consequences) + "\n"
        return {"message": f"ADR created: {title}", "adr": adr, "adr_id": adr_id}

    def handle_generate_runbook_doc(self, procedure: str = "", steps: list[str] | None = None, prerequisites: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        if not procedure:
            raise ValueError("'procedure' name is required")
        steps = steps or ["Check system status", "Execute procedure", "Verify results"]
        prerequisites = prerequisites or ["Access to production", "VPN connected"]
        doc = f"# Runbook: {procedure}\n\n"
        doc += f"**Last Updated:** {time.strftime('%Y-%m-%d')}\n\n"
        doc += "## Prerequisites\n" + "\n".join(f"- {p}" for p in prerequisites) + "\n\n"
        doc += "## Steps\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)) + "\n"
        return {"message": f"Runbook doc for '{procedure}'", "runbook": doc}

    def handle_create_glossary(self, terms: list[dict[str, str]] | None = None, **kw: Any) -> dict[str, Any]:
        terms = terms or [{"term": "SLO", "definition": "Service Level Objective"}, {"term": "MTTR", "definition": "Mean Time To Recovery"}]
        glossary = "# Glossary\n\n" + "\n".join(f"**{t['term']}** — {t['definition']}" for t in sorted(terms, key=lambda x: x.get("term", ""))) + "\n"
        return {"message": f"Glossary created with {len(terms)} terms", "glossary": glossary}
