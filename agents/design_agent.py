

from __future__ import annotations

from typing import Any

from agents import BaseAgent

class DesignAgent(BaseAgent):

    agent_name = "design_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "design",
            "status": "ready",
            "capabilities": [
                "generate_ui_brief",
                "create_design_tokens",
                "suggest_components",
                "critique_interface",
                "generate_wireframe",
            ],
        }

    def handle_generate_ui_brief(self, product: str = "", audience: str = "", tone: str = "clear", app: str = "", name: str = "", project: str = "", target: str = "", users: str = "", **kw: Any) -> dict[str, Any]:
        product = product or app or name or project or kw.get("title", "")
        audience = audience or target or users or "general users"
        if not product:
            raise ValueError("'product' (or 'app'/'name'/'project') is required")
        return {
            "message": f"Generated UI brief for {product}",
            "brief": {
                "product": product,
                "audience": audience,
                "tone": tone,
                "experience_goals": ["fast comprehension", "clear hierarchy", "obvious next actions"],
            },
        }

    def handle_create_design_tokens(self, brand: str = "", mood: str = "professional", **kw: Any) -> dict[str, Any]:
        palette = {
            "primary": "#0f766e",
            "accent": "#c2410c",
            "surface": "#f8fafc",
            "text": "#0f172a",
        }
        if mood == "playful":
            palette["accent"] = "#db2777"
        return {"message": f"Created design tokens for {brand or 'default brand'}", "tokens": {"colors": palette, "radius": "14px", "spacing_unit": "8px"}}

    def handle_suggest_components(self, page_type: str = "", **kw: Any) -> dict[str, Any]:
        if not page_type:
            raise ValueError("'page_type' is required")
        components = ["hero", "navigation", "call_to_action", "content_sections", "footer"]
        if "dashboard" in page_type.lower():
            components = ["sidebar", "metric_cards", "filters", "activity_feed", "detail_panel"]
        return {"message": f"Suggested components for {page_type}", "components": components}

    def handle_critique_interface(self, description: str = "", **kw: Any) -> dict[str, Any]:
        if not description:
            raise ValueError("'description' is required")
        issues = []
        text = description.lower()
        if "many buttons" in text:
            issues.append("too_many_primary_actions")
        if "small text" in text:
            issues.append("readability_risk")
        if not issues:
            issues.append("needs_visual_hierarchy_review")
        return {"message": "Generated interface critique", "issues": issues}

    def handle_generate_wireframe(self, page_name: str = "", sections: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        if not page_name:
            raise ValueError("'page_name' is required")
        sections = sections or ["header", "main", "sidebar", "footer"]
        wireframe = "\n".join(f"[{section.upper()}]" for section in sections)
        return {"message": f"Generated wireframe for {page_name}", "wireframe": wireframe}
