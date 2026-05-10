

from __future__ import annotations

import logging
import re
from typing import Any

from . import BaseAgent, list_agents

logger = logging.getLogger("limbi.agents.router")

_ROUTING_TABLE: dict[str, dict[str, Any]] = {
    "deploy": {
        "agent": "devops_agent",
        "suggested_action": "deploy_branch",
        "keywords": ["deploy", "release", "ship", "push to", "go live", "staging", "production"],
        "confidence_boost": 0.2,
    },
    "rollback": {
        "agent": "devops_agent",
        "suggested_action": "rollback",
        "keywords": ["rollback", "revert", "undo deploy", "go back"],
        "confidence_boost": 0.3,
    },
    "pipeline": {
        "agent": "devops_agent",
        "suggested_action": "run_pipeline",
        "keywords": ["pipeline", "ci/cd", "build", "test suite", "cicd"],
        "confidence_boost": 0.2,
    },
    "git_branch": {
        "agent": "git_agent",
        "suggested_action": "create_branch",
        "keywords": ["branch", "create branch", "new branch", "feature branch"],
        "confidence_boost": 0.2,
    },
    "git_merge": {
        "agent": "git_agent",
        "suggested_action": "merge",
        "keywords": ["merge", "pull request", "PR", "code review"],
        "confidence_boost": 0.2,
    },
    "git_pr": {
        "agent": "git_agent",
        "suggested_action": "create_pr",
        "keywords": ["pull request", "open PR", "create PR", "submit PR"],
        "confidence_boost": 0.3,
    },
    "jira_create": {
        "agent": "jira_agent",
        "suggested_action": "create_ticket",
        "keywords": ["ticket", "jira", "create ticket", "bug report", "task", "issue", "story"],
        "confidence_boost": 0.2,
    },
    "jira_search": {
        "agent": "jira_agent",
        "suggested_action": "search_tickets",
        "keywords": ["search tickets", "find ticket", "look up", "jira search"],
        "confidence_boost": 0.2,
    },
    "aws_infra": {
        "agent": "aws_agent",
        "suggested_action": "describe_instances",
        "keywords": ["ec2", "instances", "servers", "infrastructure", "aws"],
        "confidence_boost": 0.2,
    },
    "aws_lambda": {
        "agent": "aws_agent",
        "suggested_action": "invoke_lambda",
        "keywords": ["lambda", "serverless", "function", "invoke"],
        "confidence_boost": 0.2,
    },
    "aws_s3": {
        "agent": "aws_agent",
        "suggested_action": "list_s3_buckets",
        "keywords": ["s3", "bucket", "storage", "files"],
        "confidence_boost": 0.2,
    },
    "monitoring": {
        "agent": "reflex_agent",
        "suggested_action": "evaluate",
        "keywords": ["monitor", "alert", "threshold", "cpu", "memory", "health check"],
        "confidence_boost": 0.15,
    },
    "anomaly": {
        "agent": "model_reflex_agent",
        "suggested_action": "update_model",
        "keywords": ["anomaly", "abnormal", "spike", "trend", "predict", "forecast"],
        "confidence_boost": 0.2,
    },
    "plan": {
        "agent": "planner_agent",
        "suggested_action": "decompose_goal",
        "keywords": ["plan", "strategy", "breakdown", "roadmap", "steps", "decompose", "schedule"],
        "confidence_boost": 0.2,
    },
    "validate": {
        "agent": "critic_agent",
        "suggested_action": "score_response",
        "keywords": ["validate", "check", "review", "evaluate", "score", "critic", "quality"],
        "confidence_boost": 0.2,
    },
    "code": {
        "agent": "code_agent",
        "suggested_action": "generate_boilerplate",
        "keywords": ["generate code", "write code", "boilerplate", "template", "scaffold", "create script"],
        "confidence_boost": 0.2,
    },
    "code_test": {
        "agent": "code_agent",
        "suggested_action": "generate_test",
        "keywords": ["write test", "generate test", "test case", "unit test", "pytest"],
        "confidence_boost": 0.25,
    },

    "research": {
        "agent": "research_agent",
        "suggested_action": "web_search",
        "keywords": ["search", "research", "find out", "look up", "web search", "summarize article", "fact check"],
        "confidence_boost": 0.2,
    },
    "data_analysis": {
        "agent": "data_agent",
        "suggested_action": "analyze_csv",
        "keywords": ["analyze data", "csv", "statistics", "outlier", "data transform", "json data", "dataset"],
        "confidence_boost": 0.2,
    },
    "email": {
        "agent": "comms_agent",
        "suggested_action": "draft_email",
        "keywords": ["email", "draft email", "send email", "compose email", "message"],
        "confidence_boost": 0.2,
    },
    "slack": {
        "agent": "comms_agent",
        "suggested_action": "send_slack",
        "keywords": ["slack", "send slack", "notify team", "channel message", "teams"],
        "confidence_boost": 0.2,
    },
    "meeting_notes": {
        "agent": "comms_agent",
        "suggested_action": "draft_meeting_notes",
        "keywords": ["meeting notes", "meeting summary", "minutes", "action items"],
        "confidence_boost": 0.25,
    },
    "documentation": {
        "agent": "docs_agent",
        "suggested_action": "generate_readme",
        "keywords": ["readme", "documentation", "docs", "api docs", "changelog", "architecture doc", "runbook"],
        "confidence_boost": 0.2,
    },
    "testing": {
        "agent": "qa_agent",
        "suggested_action": "plan_test_strategy",
        "keywords": ["test strategy", "coverage", "regression", "test report", "qa", "quality", "benchmark"],
        "confidence_boost": 0.2,
    },
    "security_scan": {
        "agent": "security_agent",
        "suggested_action": "scan_secrets",
        "keywords": ["security", "vulnerability", "cve", "owasp", "secret scan", "dependency audit", "penetration"],
        "confidence_boost": 0.2,
    },
    "database": {
        "agent": "database_agent",
        "suggested_action": "optimize_query",
        "keywords": ["database", "sql", "query", "migration", "schema", "table", "index", "erd"],
        "confidence_boost": 0.2,
    },
    "schedule": {
        "agent": "scheduler_agent",
        "suggested_action": "create_reminder",
        "keywords": ["schedule", "reminder", "deadline", "calendar", "cron", "estimate time", "recurring"],
        "confidence_boost": 0.2,
    },
    "files": {
        "agent": "file_agent",
        "suggested_action": "list_directory",
        "keywords": ["list files", "find file", "directory", "file info", "compare files", "gitignore"],
        "confidence_boost": 0.15,
    },
    "multi_agent": {
        "agent": "swarm_agent",
        "suggested_action": "ensemble",
        "keywords": ["ensemble", "swarm", "multi-agent", "pipeline", "vote", "broadcast", "coordinate"],
        "confidence_boost": 0.2,
    },
    "memory": {
        "agent": "memory_agent",
        "suggested_action": "recall",
        "keywords": ["remember", "recall", "memory", "forget", "context", "long-term", "short-term"],
        "confidence_boost": 0.2,
    },
    "browser": {
        "agent": "browser_agent",
        "suggested_action": "summarize_page",
        "keywords": ["browser", "website", "webpage", "form", "link", "crawl"],
        "confidence_boost": 0.2,
    },
    "os": {
        "agent": "os_agent",
        "suggested_action": "system_info",
        "keywords": ["system", "os", "environment", "process", "disk", "machine"],
        "confidence_boost": 0.15,
    },
    "tool_builder": {
        "agent": "tool_builder_agent",
        "suggested_action": "generate_tool_spec",
        "keywords": ["tool", "function schema", "openapi tool", "scaffold tool", "tool contract"],
        "confidence_boost": 0.2,
    },
    "integration": {
        "agent": "integration_agent",
        "suggested_action": "design_integration",
        "keywords": ["integration", "webhook", "connector", "crm", "saas", "sync data"],
        "confidence_boost": 0.2,
    },
    "auth": {
        "agent": "auth_agent",
        "suggested_action": "review_auth_flow",
        "keywords": ["auth", "oauth", "jwt", "rbac", "permission", "secret rotation"],
        "confidence_boost": 0.2,
    },
    "observability": {
        "agent": "observability_agent",
        "suggested_action": "analyze_logs",
        "keywords": ["logs", "metrics", "alert", "incident", "slo", "trace"],
        "confidence_boost": 0.2,
    },
    "workflow": {
        "agent": "workflow_agent",
        "suggested_action": "create_workflow",
        "keywords": ["workflow", "process", "approval flow", "automation flow", "bpmn"],
        "confidence_boost": 0.2,
    },
    "approval": {
        "agent": "approval_agent",
        "suggested_action": "evaluate_approval_need",
        "keywords": ["approval", "reviewer", "sign-off", "governance", "human in the loop"],
        "confidence_boost": 0.2,
    },
    "policy": {
        "agent": "policy_agent",
        "suggested_action": "evaluate_action_policy",
        "keywords": ["policy", "compliance", "sensitive data", "retention", "regulated"],
        "confidence_boost": 0.2,
    },
    "multimodal": {
        "agent": "multimodal_agent",
        "suggested_action": "inspect_asset",
        "keywords": ["image", "audio", "video", "document", "multimodal", "pdf"],
        "confidence_boost": 0.2,
    },
    "design": {
        "agent": "design_agent",
        "suggested_action": "generate_ui_brief",
        "keywords": ["design", "ui", "ux", "wireframe", "layout", "visual"],
        "confidence_boost": 0.2,
    },
    "support": {
        "agent": "customer_support_agent",
        "suggested_action": "classify_ticket",
        "keywords": ["support", "ticket", "customer issue", "refund", "escalation"],
        "confidence_boost": 0.2,
    },
    "sales": {
        "agent": "sales_agent",
        "suggested_action": "qualify_lead",
        "keywords": ["sales", "lead", "prospect", "outreach", "proposal", "deal"],
        "confidence_boost": 0.2,
    },
    "finance": {
        "agent": "finance_agent",
        "suggested_action": "analyze_budget_variance",
        "keywords": ["finance", "budget", "invoice", "cashflow", "expense", "revenue"],
        "confidence_boost": 0.2,
    },
    "legal": {
        "agent": "legal_agent",
        "suggested_action": "flag_contract_risks",
        "keywords": ["legal", "contract", "nda", "privacy notice", "clause"],
        "confidence_boost": 0.2,
    },
    "knowledge": {
        "agent": "knowledge_agent",
        "suggested_action": "build_knowledge_map",
        "keywords": ["knowledge", "notes", "entities", "knowledge graph", "wiki"],
        "confidence_boost": 0.2,
    },
    "simulation": {
        "agent": "simulation_agent",
        "suggested_action": "run_scenario",
        "keywords": ["simulate", "scenario", "what if", "risk matrix", "sensitivity"],
        "confidence_boost": 0.2,
    },
    "evaluation": {
        "agent": "evaluation_agent",
        "suggested_action": "score_output",
        "keywords": ["evaluate", "benchmark", "rubric", "compare candidates", "regression guard"],
        "confidence_boost": 0.2,
    },
    "healthcare": {
        "agent": "healthcare_agent",
        "suggested_action": "triage_intake",
        "keywords": ["healthcare", "patient", "clinical", "visit summary", "care plan"],
        "confidence_boost": 0.2,
    },
    "education": {
        "agent": "education_agent",
        "suggested_action": "lesson_plan",
        "keywords": ["education", "lesson plan", "curriculum", "quiz", "learning path"],
        "confidence_boost": 0.2,
    },
    "hr": {
        "agent": "hr_agent",
        "suggested_action": "onboarding_plan",
        "keywords": ["hr", "employee", "onboarding", "leave", "performance review"],
        "confidence_boost": 0.2,
    },
    "recruiting": {
        "agent": "recruiting_agent",
        "suggested_action": "score_candidate",
        "keywords": ["recruiting", "candidate", "interview", "hiring", "talent"],
        "confidence_boost": 0.2,
    },
    "procurement": {
        "agent": "procurement_agent",
        "suggested_action": "vendor_scorecard",
        "keywords": ["procurement", "vendor", "rfq", "purchase", "sourcing"],
        "confidence_boost": 0.2,
    },
    "real_estate": {
        "agent": "real_estate_agent",
        "suggested_action": "listing_summary",
        "keywords": ["real estate", "property", "listing", "rental", "buyer"],
        "confidence_boost": 0.2,
    },
    "ecommerce": {
        "agent": "ecommerce_agent",
        "suggested_action": "catalog_audit",
        "keywords": ["ecommerce", "shop", "catalog", "merchandising", "conversion"],
        "confidence_boost": 0.2,
    },
    "marketing": {
        "agent": "marketing_agent",
        "suggested_action": "campaign_brief",
        "keywords": ["marketing", "campaign", "persona", "channel mix", "content calendar"],
        "confidence_boost": 0.2,
    },
    "social_media": {
        "agent": "social_media_agent",
        "suggested_action": "draft_post",
        "keywords": ["social media", "post", "comments", "moderation", "instagram", "linkedin"],
        "confidence_boost": 0.2,
    },
    "blockchain": {
        "agent": "blockchain_agent",
        "suggested_action": "wallet_risk_review",
        "keywords": ["blockchain", "wallet", "token", "smart contract", "web3"],
        "confidence_boost": 0.2,
    },
    "iot": {
        "agent": "iot_agent",
        "suggested_action": "fleet_summary",
        "keywords": ["iot", "device fleet", "telemetry", "firmware", "edge"],
        "confidence_boost": 0.2,
    },
    "travel": {
        "agent": "travel_agent",
        "suggested_action": "itinerary_builder",
        "keywords": ["travel", "itinerary", "trip", "packing", "flight"],
        "confidence_boost": 0.2,
    },
    "manufacturing": {
        "agent": "manufacturing_agent",
        "suggested_action": "production_plan",
        "keywords": ["manufacturing", "production", "factory", "maintenance", "quality line"],
        "confidence_boost": 0.2,
    },
    "customer_success": {
        "agent": "customer_success_agent",
        "suggested_action": "health_score",
        "keywords": ["customer success", "renewal", "qbr", "adoption", "health score"],
        "confidence_boost": 0.2,
    },
    "insurance": {
        "agent": "insurance_agent",
        "suggested_action": "claim_intake",
        "keywords": ["insurance", "claim", "underwriting", "policy", "fraud"],
        "confidence_boost": 0.2,
    },
    "logistics": {
        "agent": "logistics_agent",
        "suggested_action": "route_plan",
        "keywords": ["logistics", "shipment", "warehouse", "route", "supply chain"],
        "confidence_boost": 0.2,
    },
    "hospitality": {
        "agent": "hospitality_agent",
        "suggested_action": "guest_itinerary",
        "keywords": ["hospitality", "guest", "hotel", "occupancy", "service recovery"],
        "confidence_boost": 0.2,
    },
    "agriculture": {
        "agent": "agriculture_agent",
        "suggested_action": "crop_plan",
        "keywords": ["agriculture", "farm", "crop", "field", "harvest"],
        "confidence_boost": 0.2,
    },
    "media": {
        "agent": "media_agent",
        "suggested_action": "editorial_brief",
        "keywords": ["media", "editorial", "content production", "distribution", "audience"],
        "confidence_boost": 0.2,
    },
    "government": {
        "agent": "government_agent",
        "suggested_action": "policy_brief",
        "keywords": ["government", "public sector", "grant", "constituent", "service request"],
        "confidence_boost": 0.2,
    },
    "mutation": {
        "agent": "mutation_agent",
        "suggested_action": "detect_missing",
        "keywords": ["create agent", "new agent", "missing agent", "evolve agent", "self mutation", "auto generate agent", "scaffold agent"],
        "confidence_boost": 0.3,
    },
}

class RouterAgent(BaseAgent):

    agent_name = "router_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "intelligent_router",
            "status": "ready",
            "routing_rules": len(_ROUTING_TABLE),
            "registered_agents": list(list_agents().keys()),
        }

    def handle_route(
        self,
        query: str = "",
        top_k: int = 3,
        threshold: float = 0.1,
        **kw: Any,
    ) -> dict[str, Any]:

        if not query:
            raise ValueError("A 'query' is required for routing")

        query_lower = query.lower()
        scored: list[dict[str, Any]] = []

        for intent, route in _ROUTING_TABLE.items():
            score = 0.0
            matched_keywords: list[str] = []

            for keyword in route["keywords"]:
                if keyword.lower() in query_lower:

                    match_score = len(keyword.split()) * 0.15 + 0.1
                    score += match_score
                    matched_keywords.append(keyword)

            if matched_keywords:
                score += route.get("confidence_boost", 0)

            if score >= threshold:
                scored.append({
                    "intent": intent,
                    "agent": route["agent"],
                    "suggested_action": route["suggested_action"],
                    "confidence": round(min(score, 1.0), 3),
                    "matched_keywords": matched_keywords,
                })

        scored.sort(key=lambda x: x["confidence"], reverse=True)
        top = scored[:top_k]

        if not top:
            return {
                "message": "No confident routing match - using LLM orchestrator for general handling",
                "query": query,
                "suggestions": [],
                "fallback": "orchestrator",
            }

        primary = top[0]
        return {
            "message": f"Routed to {primary['agent']}.{primary['suggested_action']} (confidence: {primary['confidence']})",
            "query": query,
            "primary_route": primary,
            "alternatives": top[1:],
            "total_matches": len(scored),
        }

    def handle_classify_intent(
        self,
        query: str = "",
        **kw: Any,
    ) -> dict[str, Any]:

        if not query:
            raise ValueError("A 'query' is required")

        query_lower = query.lower()

        categories = {
            "action": ["deploy", "create", "merge", "delete", "update", "run", "execute", "invoke"],
            "query": ["show", "list", "get", "find", "search", "status", "describe", "check"],
            "analysis": ["analyze", "evaluate", "score", "predict", "compare", "measure"],
            "planning": ["plan", "schedule", "roadmap", "strategy", "breakdown"],
            "conversation": ["explain", "help", "what is", "how to", "why", "tell me"],
        }

        detected: dict[str, float] = {}
        for category, keywords in categories.items():
            score = sum(0.2 for kw in keywords if kw in query_lower)
            if score > 0:
                detected[category] = round(min(score, 1.0), 2)

        if not detected:
            detected["conversation"] = 0.5

        primary = max(detected, key=detected.get)

        return {
            "query": query,
            "primary_intent": primary,
            "confidence": detected[primary],
            "all_intents": detected,
            "requires_delegation": primary in ("action", "analysis", "planning"),
        }

    def handle_get_routing_table(self, **kw: Any) -> dict[str, Any]:

        return {
            "routes": {
                intent: {
                    "agent": r["agent"],
                    "action": r["suggested_action"],
                    "keywords": r["keywords"],
                }
                for intent, r in _ROUTING_TABLE.items()
            },
            "total_routes": len(_ROUTING_TABLE),
        }

    def handle_fan_out(
        self,
        query: str = "",
        agents: list[str] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        if not query:
            raise ValueError("A 'query' is required")

        route_result = self.handle_route(query=query, top_k=5, threshold=0.05)
        suggestions = route_result.get("suggestions") or [route_result.get("primary_route")]
        suggestions = [s for s in suggestions if s]

        if agents:

            suggestions = [s for s in suggestions if s["agent"] in agents]

        seen_agents: set[str] = set()
        unique: list[dict[str, Any]] = []
        for s in suggestions:
            if s["agent"] not in seen_agents:
                seen_agents.add(s["agent"])
                unique.append(s)

        return {
            "message": f"Fan-out to {len(unique)} agents",
            "query": query,
            "targets": unique,
            "parallel_execution": True,
        }
