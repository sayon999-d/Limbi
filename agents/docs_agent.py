

from __future__ import annotations

import logging
import time
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.docs")

class DocsAgent(BaseAgent):

    agent_name = "docs_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "documentation",
            "status": "ready",
            "capabilities": [
                "generate_readme", "generate_api_docs",
                "generate_changelog", "generate_architecture",
                "generate_runbook",
            ],
        }

    def handle_generate_readme(
        self,
        project_name: str = "",
        description: str = "",
        tech_stack: list[str] | None = None,
        features: list[str] | None = None,
        installation_steps: list[str] | None = None,
        license_type: str = "MIT",
        **kw: Any,
    ) -> dict[str, Any]:

        if not project_name:
            raise ValueError("'project_name' is required")

        tech_stack = tech_stack or ["Python"]
        features = features or ["Core functionality"]
        installation_steps = installation_steps or [
            "Clone the repository",
            "Install dependencies: `pip install -r requirements.txt`",
            "Configure environment: `cp .env.example .env`",
            "Run the application",
        ]

        badges = self._generate_badges(project_name, tech_stack, license_type)

        readme = f"""# {project_name}

{badges}

{description or f'{project_name} - A powerful application.'}

##  Features

{chr(10).join(f'- {f}' for f in features)}

##  Tech Stack

{chr(10).join(f'- **{t}**' for t in tech_stack)}

##  Installation

{chr(10).join(f'{i+1}. {step}' for i, step in enumerate(installation_steps))}

##  Quick Start

```bash
git clone https://github.com/your-org/{project_name.lower().replace(' ', '-')}.git
cd {project_name.lower().replace(' ', '-')}

pip install -r requirements.txt

python main.py
```

##  Documentation

For full documentation, visit the [docs](./docs/).

##  Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

##  License

This project is licensed under the {license_type} License - see the [LICENSE](LICENSE) file for details.

---

Built by the {project_name} team
"""

        return {
            "message": f"README generated for '{project_name}'",
            "readme": readme,
            "sections": ["Features", "Tech Stack", "Installation", "Quick Start",
                         "Documentation", "Contributing", "License"],
            "word_count": len(readme.split()),
        }

    def handle_generate_api_docs(
        self,
        endpoints: list[dict[str, str]] | None = None,
        base_url: str = "http://localhost:8000",
        title: str = "API Documentation",
        **kw: Any,
    ) -> dict[str, Any]:

        endpoints = endpoints or []

        doc = f"# {title}\n\n"
        doc += f"**Base URL:** `{base_url}`\n\n"
        doc += "---\n\n"

        for i, ep in enumerate(endpoints, 1):
            method = ep.get("method", "GET").upper()
            path = ep.get("path", "/")
            desc = ep.get("description", "")
            params = ep.get("params", "")

            doc += f"## {i}. {method} `{path}`\n\n"
            doc += f"{desc}\n\n"

            if params:
                doc += f"**Parameters:**\n```json\n{params}\n```\n\n"

            doc += f"**Example:**\n```bash\ncurl -X {method} {base_url}{path}\n```\n\n"
            doc += "---\n\n"

        return {
            "message": f"API docs generated with {len(endpoints)} endpoints",
            "documentation": doc,
            "endpoint_count": len(endpoints),
        }

    def handle_generate_changelog(
        self,
        version: str = "",
        date: str = "",
        added: list[str] | None = None,
        changed: list[str] | None = None,
        fixed: list[str] | None = None,
        removed: list[str] | None = None,
        security: list[str] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        if not version:
            raise ValueError("'version' is required")

        date = date or time.strftime("%Y-%m-%d")

        entry = f"## [{version}] - {date}\n\n"

        sections = [
            ("Added", added), ("Changed", changed),
            ("Fixed", fixed), ("Removed", removed),
            ("Security", security),
        ]

        for title, items in sections:
            if items:
                entry += f"### {title}\n"
                for item in items:
                    entry += f"- {item}\n"
                entry += "\n"

        return {
            "message": f"Changelog entry created for v{version}",
            "entry": entry,
            "version": version,
            "date": date,
            "total_items": sum(len(s or []) for _, s in sections),
        }

    def handle_generate_architecture(
        self,
        project_name: str = "",
        components: list[dict[str, str]] | None = None,
        data_flow: str = "",
        tech_decisions: list[dict[str, str]] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        components = components or []
        tech_decisions = tech_decisions or []

        doc = f"# {project_name or 'System'} Architecture\n\n"
        doc += f"**Last Updated:** {time.strftime('%Y-%m-%d')}\n\n"

        doc += "## System Overview\n\n"
        if components:
            doc += "| Component | Type | Description |\n"
            doc += "|-----------|------|-------------|\n"
            for c in components:
                doc += f"| {c.get('name', '')} | {c.get('type', '')} | {c.get('description', '')} |\n"
            doc += "\n"

        if data_flow:
            doc += "## Data Flow\n\n"
            doc += f"{data_flow}\n\n"

        if tech_decisions:
            doc += "## Architecture Decision Records (ADRs)\n\n"
            for i, td in enumerate(tech_decisions, 1):
                doc += f"### ADR-{i:03d}: {td.get('decision', '')}\n\n"
                doc += f"**Rationale:** {td.get('rationale', '')}\n\n"
                doc += f"**Alternatives considered:** {td.get('alternatives', 'None documented')}\n\n"

        return {
            "message": f"Architecture doc generated for '{project_name}'",
            "documentation": doc,
            "components": len(components),
            "adr_count": len(tech_decisions),
        }

    def handle_generate_runbook(
        self,
        service_name: str = "",
        scenarios: list[dict[str, Any]] | None = None,
        contacts: list[dict[str, str]] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        if not service_name:
            raise ValueError("'service_name' is required")

        scenarios = scenarios or []
        contacts = contacts or []

        doc = f"# Runbook: {service_name}\n\n"
        doc += f"**Last Updated:** {time.strftime('%Y-%m-%d')}\n\n"

        if contacts:
            doc += "## Contacts\n\n"
            doc += "| Role | Name | Contact |\n"
            doc += "|------|------|---------|\n"
            for c in contacts:
                doc += f"| {c.get('role', '')} | {c.get('name', '')} | {c.get('contact', '')} |\n"
            doc += "\n"

        if scenarios:
            doc += "## Incident Scenarios\n\n"
            for s in scenarios:
                severity = s.get("severity", "medium")
                doc += f"###  {s.get('title', 'Unnamed')} (Severity: {severity})\n\n"

                if s.get("symptoms"):
                    doc += "**Symptoms:**\n"
                    for symptom in s["symptoms"]:
                        doc += f"- {symptom}\n"
                    doc += "\n"

                if s.get("steps"):
                    doc += "**Resolution Steps:**\n"
                    for i, step in enumerate(s["steps"], 1):
                        doc += f"{i}. {step}\n"
                    doc += "\n"

        return {
            "message": f"Runbook generated for '{service_name}'",
            "runbook": doc,
            "scenarios": len(scenarios),
            "contacts": len(contacts),
        }

    def _generate_badges(self, name: str, stack: list[str], license_type: str) -> str:
        badges = []
        slug = name.lower().replace(" ", "-")
        badges.append(f"![License](https://img.shields.io/badge/license-{license_type}-blue.svg)")
        for tech in stack[:3]:
            badges.append(f"![{tech}](https://img.shields.io/badge/-{tech}-informational)")
        return " ".join(badges)
