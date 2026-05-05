from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.onboarding")


class OnboardingAgent(BaseAgent):

    agent_name = "onboarding_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "onboarding", "status": "ready", "capabilities": ["create_onboarding_plan", "setup_dev_environment", "generate_welcome_pack", "create_checklist", "knowledge_transfer"]}

    def handle_create_onboarding_plan(self, employee_name: str = "", role: str = "", department: str = "", start_date: str = "", **kw: Any) -> dict[str, Any]:
        if not employee_name:
            raise ValueError("'employee_name' is required")
        weeks = [
            {"week": 1, "focus": "Orientation & Setup", "tasks": ["IT setup", "HR paperwork", "Team introductions", "Access provisioning"]},
            {"week": 2, "focus": "Learning & Context", "tasks": ["Codebase walkthrough", "Architecture overview", "Read key docs", "Shadow team member"]},
            {"week": 3, "focus": "First Contributions", "tasks": ["Pick starter ticket", "Submit first PR", "Attend sprint ceremonies", "1:1 with manager"]},
            {"week": 4, "focus": "Independence", "tasks": ["Own a small feature", "Code review others", "Write a doc", "30-day feedback session"]},
        ]
        return {"message": f"Onboarding plan for {employee_name} ({role})", "employee": employee_name, "role": role, "department": department, "start_date": start_date, "plan": weeks}

    def handle_setup_dev_environment(self, role: str = "backend", os_type: str = "mac", **kw: Any) -> dict[str, Any]:
        base_tools = ["Git", "VS Code", "Docker", "Slack", "1Password"]
        role_tools = {"backend": ["Python 3.12", "Poetry", "PostgreSQL", "Redis", "Postman"], "frontend": ["Node.js 20", "pnpm", "Chrome DevTools", "Figma"], "devops": ["Terraform", "kubectl", "AWS CLI", "Helm"], "data": ["Python 3.12", "Jupyter", "DBeaver", "Spark"]}
        tools = base_tools + role_tools.get(role, [])
        return {"message": f"Dev environment setup for {role} on {os_type}", "role": role, "os": os_type, "tools": tools, "total_tools": len(tools)}

    def handle_generate_welcome_pack(self, name: str = "", team: str = "", buddy: str = "", **kw: Any) -> dict[str, Any]:
        pack = f"# Welcome to the team, {name or 'New Hire'}! 🎉\n\n"
        pack += f"**Team:** {team or 'Engineering'}\n"
        pack += f"**Buddy:** {buddy or 'TBD'}\n\n"
        pack += "## Key Links\n- Internal Wiki\n- Codebase (GitHub)\n- CI/CD Dashboard\n- Monitoring\n- Slack Channels\n\n"
        pack += "## First Week Checklist\n- [ ] Set up laptop\n- [ ] Join Slack channels\n- [ ] Read the README\n- [ ] Meet your buddy\n- [ ] Complete HR onboarding\n"
        return {"message": f"Welcome pack generated for {name or 'new hire'}", "welcome_pack": pack}

    def handle_create_checklist(self, category: str = "general", items: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        default_items = {"general": ["Laptop setup", "Email access", "Slack access", "Git access", "VPN configured"], "security": ["MFA enabled", "SSH keys generated", "Security training completed", "NDA signed"], "compliance": ["Data handling training", "Code of conduct acknowledged", "Privacy policy reviewed"]}
        final_items = items or default_items.get(category, default_items["general"])
        return {"message": f"Checklist ({category}): {len(final_items)} items", "category": category, "checklist": [{"item": i, "completed": False} for i in final_items]}

    def handle_knowledge_transfer(self, topic: str = "", from_person: str = "", to_person: str = "", sessions: int = 3, **kw: Any) -> dict[str, Any]:
        if not topic:
            raise ValueError("'topic' is required")
        plan = [{"session": i+1, "focus": f"Session {i+1}: {'Overview' if i==0 else 'Deep dive' if i==1 else 'Hands-on'}", "duration": "1 hour", "deliverable": ["Documentation", "Recording", "Q&A notes"][i % 3]} for i in range(sessions)]
        return {"message": f"Knowledge transfer plan: '{topic}' ({sessions} sessions)", "topic": topic, "from": from_person, "to": to_person, "sessions": plan}
