

from __future__ import annotations

import logging
import math
import time
from typing import Any

from . import BaseAgent

logger = logging.getLogger("limbi.agents.qa")

class QAAgent(BaseAgent):

    agent_name = "qa_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "quality_assurance",
            "status": "ready",
            "capabilities": [
                "plan_test_strategy", "analyze_coverage",
                "detect_regression", "generate_test_report",
                "benchmark",
            ],
        }

    def handle_plan_test_strategy(
        self,
        feature: str = "",
        feature_type: str = "api",
        risk_level: str = "medium",
        **kw: Any,
    ) -> dict[str, Any]:

        if not feature:
            raise ValueError("A 'feature' description is required")

        test_matrix: dict[str, list[dict[str, str]]] = {
            "api": [
                {"type": "unit", "scope": "Handler functions", "priority": "P0"},
                {"type": "integration", "scope": "API -> Service -> DB flow", "priority": "P0"},
                {"type": "contract", "scope": "Request/response schema validation", "priority": "P1"},
                {"type": "load", "scope": "Concurrent request handling", "priority": "P2"},
                {"type": "security", "scope": "Auth, input validation, injection", "priority": "P1"},
            ],
            "ui": [
                {"type": "unit", "scope": "Component rendering", "priority": "P0"},
                {"type": "e2e", "scope": "Full user workflows", "priority": "P0"},
                {"type": "visual", "scope": "Screenshot comparison", "priority": "P2"},
                {"type": "accessibility", "scope": "WCAG compliance", "priority": "P1"},
                {"type": "cross-browser", "scope": "Chrome, Firefox, Safari", "priority": "P1"},
            ],
            "integration": [
                {"type": "integration", "scope": "Service-to-service calls", "priority": "P0"},
                {"type": "contract", "scope": "API contract verification", "priority": "P0"},
                {"type": "chaos", "scope": "Failure injection", "priority": "P2"},
                {"type": "data_integrity", "scope": "End-to-end data consistency", "priority": "P1"},
            ],
            "data": [
                {"type": "validation", "scope": "Schema and type checking", "priority": "P0"},
                {"type": "boundary", "scope": "Edge cases and null handling", "priority": "P0"},
                {"type": "migration", "scope": "Data migration correctness", "priority": "P1"},
                {"type": "performance", "scope": "Query execution time", "priority": "P1"},
            ],
            "security": [
                {"type": "penetration", "scope": "Vulnerability scanning", "priority": "P0"},
                {"type": "auth", "scope": "Authentication and authorization", "priority": "P0"},
                {"type": "injection", "scope": "SQL/XSS/CSRF injection", "priority": "P0"},
                {"type": "dependency", "scope": "Dependency vulnerability audit", "priority": "P1"},
            ],
        }

        tests = test_matrix.get(feature_type, test_matrix["api"])

        if risk_level in ("high", "critical"):
            tests.append({"type": "regression", "scope": "Full regression suite", "priority": "P0"})
            tests.append({"type": "rollback", "scope": "Verify rollback procedures", "priority": "P1"})

        estimated_hours = len(tests) * (1.5 if risk_level in ("high", "critical") else 1.0)

        return {
            "message": f"Test strategy for '{feature}' ({feature_type}, risk={risk_level})",
            "feature": feature,
            "feature_type": feature_type,
            "risk_level": risk_level,
            "test_plan": tests,
            "total_test_types": len(tests),
            "estimated_effort_hours": round(estimated_hours, 1),
            "recommendation": "Requires full regression" if risk_level == "critical" else "Standard coverage sufficient",
        }

    def handle_analyze_coverage(
        self,
        total_lines: int = 0,
        covered_lines: int = 0,
        total_functions: int = 0,
        covered_functions: int = 0,
        total_branches: int = 0,
        covered_branches: int = 0,
        uncovered_files: list[str] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        line_cov = (covered_lines / max(total_lines, 1)) * 100
        func_cov = (covered_functions / max(total_functions, 1)) * 100
        branch_cov = (covered_branches / max(total_branches, 1)) * 100
        overall = (line_cov + func_cov + branch_cov) / 3

        grade = "A" if overall >= 90 else "B" if overall >= 75 else "C" if overall >= 60 else "D" if overall >= 40 else "F"
        recommendations: list[str] = []

        if line_cov < 80:
            recommendations.append(f"Line coverage ({line_cov:.1f}%) is below 80% - add more unit tests")
        if func_cov < 90:
            recommendations.append(f"Function coverage ({func_cov:.1f}%) is below 90% - test all public functions")
        if branch_cov < 70:
            recommendations.append(f"Branch coverage ({branch_cov:.1f}%) is below 70% - test conditional paths")
        if uncovered_files:
            recommendations.append(f"{len(uncovered_files)} files have zero coverage")

        return {
            "message": f"Coverage analysis: {overall:.1f}% (grade: {grade})",
            "overall_coverage": round(overall, 1),
            "grade": grade,
            "line_coverage": round(line_cov, 1),
            "function_coverage": round(func_cov, 1),
            "branch_coverage": round(branch_cov, 1),
            "uncovered_files": uncovered_files or [],
            "recommendations": recommendations,
            "meets_threshold": overall >= 80,
        }

    def handle_detect_regression(
        self,
        before: dict[str, float] | None = None,
        after: dict[str, float] | None = None,
        tolerance_percent: float = 5.0,
        **kw: Any,
    ) -> dict[str, Any]:

        if not before or not after:
            raise ValueError("Both 'before' and 'after' metric dicts are required")

        regressions: list[dict[str, Any]] = []
        improvements: list[dict[str, Any]] = []

        for metric in set(before.keys()) | set(after.keys()):
            b = before.get(metric)
            a = after.get(metric)
            if b is None or a is None:
                continue

            if b == 0:
                change_pct = 100.0 if a > 0 else 0.0
            else:
                change_pct = ((a - b) / abs(b)) * 100

            entry = {
                "metric": metric,
                "before": b,
                "after": a,
                "change_percent": round(change_pct, 1),
            }

            positive_higher = metric in ("throughput", "success_rate", "uptime", "coverage")

            if positive_higher:
                if change_pct < -tolerance_percent:
                    entry["status"] = "regression"
                    regressions.append(entry)
                elif change_pct > tolerance_percent:
                    entry["status"] = "improvement"
                    improvements.append(entry)
            else:
                if change_pct > tolerance_percent:
                    entry["status"] = "regression"
                    regressions.append(entry)
                elif change_pct < -tolerance_percent:
                    entry["status"] = "improvement"
                    improvements.append(entry)

        verdict = "regression_detected" if regressions else "no_regression"

        return {
            "message": f"{len(regressions)} regressions, {len(improvements)} improvements detected",
            "verdict": verdict,
            "regressions": regressions,
            "improvements": improvements,
            "tolerance_percent": tolerance_percent,
            "safe_to_deploy": len(regressions) == 0,
        }

    def handle_generate_test_report(
        self,
        suite_name: str = "",
        total_tests: int = 0,
        passed: int = 0,
        failed: int = 0,
        skipped: int = 0,
        duration_seconds: float = 0,
        failures: list[dict[str, str]] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        pass_rate = (passed / max(total_tests, 1)) * 100
        failures = failures or []

        verdict = "PASS" if failed == 0 else "FAIL"
        emoji = "" if verdict == "PASS" else ""

        report = f"# {emoji} Test Report: {suite_name or 'Test Suite'}\n\n"
        report += f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"**Duration:** {duration_seconds:.1f}s\n"
        report += f"**Verdict:** {verdict}\n\n"

        report += "## Summary\n\n"
        report += f"| Metric | Value |\n|--------|-------|\n"
        report += f"| Total Tests | {total_tests} |\n"
        report += f"| Passed | {passed}  |\n"
        report += f"| Failed | {failed}  |\n"
        report += f"| Skipped | {skipped}  |\n"
        report += f"| Pass Rate | {pass_rate:.1f}% |\n\n"

        if failures:
            report += "## Failed Tests\n\n"
            for f in failures:
                report += f"###  {f.get('test', 'Unknown')}\n"
                report += f"**Error:** {f.get('error', 'No details')}\n\n"

        return {
            "message": f"Test report: {verdict} ({pass_rate:.1f}% pass rate)",
            "report": report,
            "verdict": verdict,
            "pass_rate": round(pass_rate, 1),
            "total": total_tests,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        }

    def handle_benchmark(
        self,
        operation: str = "noop",
        iterations: int = 1000,
        **kw: Any,
    ) -> dict[str, Any]:

        import hashlib
        import json as json_mod

        iterations = min(iterations, 100000)

        start = time.perf_counter()
        for _ in range(iterations):
            if operation == "hash":
                hashlib.sha256(b"benchmark data " * 10).hexdigest()
            elif operation == "sort":
                sorted([i % 100 for i in range(100)])
            elif operation == "json_parse":
                json_mod.loads('{"key": "value", "num": 42, "arr": [1, 2, 3]}')
            else:
                pass
        elapsed = time.perf_counter() - start

        ops_per_sec = iterations / elapsed if elapsed > 0 else 0

        return {
            "message": f"Benchmark: {operation}  {iterations} in {elapsed*1000:.1f}ms",
            "operation": operation,
            "iterations": iterations,
            "total_time_ms": round(elapsed * 1000, 2),
            "avg_time_us": round((elapsed / iterations) * 1_000_000, 2),
            "ops_per_second": round(ops_per_sec),
        }
