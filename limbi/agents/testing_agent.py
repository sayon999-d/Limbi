from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from . import BaseAgent

logger = logging.getLogger("limbi.agents.testing")

_test_suites: dict[str, dict[str, Any]] = {}
_test_runs: list[dict[str, Any]] = []


class TestingAgent(BaseAgent):

    agent_name = "testing_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "testing",
            "status": "ready",
            "test_suites": len(_test_suites),
            "total_runs": len(_test_runs),
            "capabilities": [
                "generate_test_plan", "create_test_cases",
                "api_test_suite", "load_test_config", "coverage_report",
            ],
        }

    def handle_generate_test_plan(
        self,
        feature: str = "",
        test_types: list[str] | None = None,
        priority: str = "medium",
        **kw: Any,
    ) -> dict[str, Any]:
        if not feature:
            raise ValueError("A 'feature' description is required")

        test_types = test_types or ["unit", "integration", "e2e", "regression"]
        plan_id = str(uuid.uuid4())[:8]

        plan = {
            "id": plan_id,
            "feature": feature,
            "priority": priority,
            "test_types": test_types,
            "sections": [],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        section_templates = {
            "unit": {"name": "Unit Tests", "scope": "Individual functions and methods", "count": 8},
            "integration": {"name": "Integration Tests", "scope": "Component interactions and API contracts", "count": 5},
            "e2e": {"name": "End-to-End Tests", "scope": "Full user workflows through the system", "count": 3},
            "regression": {"name": "Regression Tests", "scope": "Previously broken scenarios", "count": 4},
            "performance": {"name": "Performance Tests", "scope": "Response time and throughput benchmarks", "count": 3},
            "security": {"name": "Security Tests", "scope": "Auth, injection, access control", "count": 4},
        }

        for tt in test_types:
            tmpl = section_templates.get(tt, {"name": tt.title(), "scope": f"{tt} testing", "count": 3})
            plan["sections"].append({**tmpl, "status": "planned"})

        total_cases = sum(s["count"] for s in plan["sections"])
        return {
            "message": f"Test plan for '{feature}': {len(test_types)} types, ~{total_cases} test cases",
            "plan": plan,
            "estimated_effort_hours": total_cases * 0.5,
        }

    def handle_create_test_cases(
        self,
        component: str = "",
        scenarios: list[str] | None = None,
        framework: str = "pytest",
        **kw: Any,
    ) -> dict[str, Any]:
        if not component:
            raise ValueError("A 'component' name is required")

        scenarios = scenarios or [
            "happy path with valid input",
            "empty input handling",
            "invalid input type",
            "boundary values",
            "concurrent access",
        ]

        test_cases: list[dict[str, Any]] = []
        for i, scenario in enumerate(scenarios):
            test_cases.append({
                "id": f"TC-{i + 1:03d}",
                "scenario": scenario,
                "component": component,
                "preconditions": "Component initialized",
                "expected_result": "As specified",
                "priority": "high" if i == 0 else "medium",
                "automated": True,
            })

        return {
            "message": f"Created {len(test_cases)} test cases for '{component}'",
            "component": component,
            "framework": framework,
            "test_cases": test_cases,
        }

    def handle_api_test_suite(
        self,
        base_url: str = "http://localhost:8000",
        endpoints: list[dict[str, str]] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:
        endpoints = endpoints or [
            {"method": "GET", "path": "/health"},
            {"method": "GET", "path": "/api/agents"},
            {"method": "POST", "path": "/api/chat", "body": '{"message": "hello"}'},
        ]

        suite_id = str(uuid.uuid4())[:8]
        tests: list[dict[str, Any]] = []
        for ep in endpoints:
            method = ep.get("method", "GET")
            path = ep.get("path", "/")
            tests.append({
                "name": f"test_{method.lower()}_{path.replace('/', '_').strip('_')}",
                "method": method,
                "url": f"{base_url}{path}",
                "expected_status": 200,
                "body": ep.get("body"),
                "assertions": ["status_code == 200", "response_time < 2000ms"],
            })

        suite = {
            "id": suite_id,
            "base_url": base_url,
            "tests": tests,
            "total": len(tests),
        }
        _test_suites[suite_id] = suite

        return {
            "message": f"API test suite created with {len(tests)} tests",
            "suite": suite,
        }

    def handle_load_test_config(
        self,
        target_url: str = "",
        concurrent_users: int = 50,
        duration_seconds: int = 60,
        ramp_up_seconds: int = 10,
        **kw: Any,
    ) -> dict[str, Any]:
        if not target_url:
            raise ValueError("A 'target_url' is required")

        config = {
            "tool": "locust",
            "target": target_url,
            "concurrent_users": concurrent_users,
            "duration_seconds": duration_seconds,
            "ramp_up_seconds": ramp_up_seconds,
            "thresholds": {
                "p95_response_time_ms": 500,
                "p99_response_time_ms": 1000,
                "error_rate_percent": 1.0,
                "min_rps": concurrent_users * 2,
            },
            "script": self._generate_locust_script(target_url),
        }

        return {
            "message": f"Load test config: {concurrent_users} users, {duration_seconds}s against {target_url}",
            "config": config,
        }

    def handle_coverage_report(
        self,
        total_lines: int = 0,
        covered_lines: int = 0,
        modules: list[dict[str, Any]] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:
        modules = modules or []
        overall_coverage = round(covered_lines / max(total_lines, 1) * 100, 1)

        report = {
            "overall_coverage": f"{overall_coverage}%",
            "total_lines": total_lines,
            "covered_lines": covered_lines,
            "uncovered_lines": total_lines - covered_lines,
            "modules": modules,
            "status": "pass" if overall_coverage >= 80 else "fail",
            "threshold": "80%",
        }

        return {
            "message": f"Coverage report: {overall_coverage}% ({'PASS' if overall_coverage >= 80 else 'FAIL'})",
            "report": report,
            "recommendation": "Increase coverage" if overall_coverage < 80 else "Coverage meets threshold",
        }

    def _generate_locust_script(self, target_url: str) -> str:
        return f'''from locust import HttpUser, task, between

class LoadTestUser(HttpUser):
    wait_time = between(1, 3)
    host = "{target_url}"

    @task(3)
    def health_check(self):
        self.client.get("/health")

    @task(1)
    def chat(self):
        self.client.post("/api/chat", json={{"message": "test"}})
'''
