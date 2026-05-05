

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Any

from . import BaseAgent

class ObservabilityAgent(BaseAgent):

    agent_name = "observability_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "observability",
            "status": "ready",
            "capabilities": [
                "analyze_logs",
                "summarize_metrics",
                "create_alert_policy",
                "build_incident_timeline",
                "review_slo",
            ],
        }

    def handle_analyze_logs(self, logs: str = "", **kw: Any) -> dict[str, Any]:
        if not logs:
            raise ValueError("'logs' is required")

        lines = [line for line in logs.splitlines() if line.strip()]
        severities = Counter()
        patterns = []
        for line in lines:
            upper = line.upper()
            if "ERROR" in upper:
                severities["error"] += 1
            elif "WARN" in upper:
                severities["warning"] += 1
            else:
                severities["info"] += 1
            if "timeout" in line.lower():
                patterns.append("timeout")
            if "429" in line:
                patterns.append("rate_limit")
            if "connection" in line.lower():
                patterns.append("connection")

        return {
            "message": f"Analyzed {len(lines)} log lines",
            "severity_counts": dict(severities),
            "common_patterns": Counter(patterns).most_common(5),
            "sample_errors": [line for line in lines if "ERROR" in line.upper()][:5],
        }

    def handle_summarize_metrics(self, metrics: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        metrics = metrics or []
        if not metrics:
            raise ValueError("'metrics' is required")

        summary = []
        for item in metrics:
            values = item.get("values", [])
            if not values:
                continue
            avg = sum(values) / len(values)
            summary.append({
                "metric": item.get("metric", "unknown"),
                "avg": round(avg, 3),
                "min": min(values),
                "max": max(values),
                "latest": values[-1],
            })
        return {"message": f"Summarized {len(summary)} metrics", "summary": summary}

    def handle_create_alert_policy(self, service: str = "", metric: str = "", threshold: float = 0.0, **kw: Any) -> dict[str, Any]:
        if not service or not metric:
            raise ValueError("'service' and 'metric' are required")

        return {
            "message": f"Created alert policy for {service}",
            "policy": {
                "service": service,
                "metric": metric,
                "threshold": threshold,
                "condition": f"Trigger when {metric} exceeds {threshold} for 5 minutes",
                "severity": "high",
            },
        }

    def handle_build_incident_timeline(self, events: list[dict[str, str]] | None = None, **kw: Any) -> dict[str, Any]:
        events = events or []
        ordered = sorted(events, key=lambda item: item.get("timestamp", ""))
        return {
            "message": f"Built timeline with {len(ordered)} events",
            "timeline": ordered,
            "first_event": ordered[0]["timestamp"] if ordered else None,
            "last_event": ordered[-1]["timestamp"] if ordered else None,
        }

    def handle_review_slo(self, target_percent: float = 99.9, downtime_minutes: int = 0, period_days: int = 30, **kw: Any) -> dict[str, Any]:
        total_minutes = period_days * 24 * 60
        availability = round(((total_minutes - downtime_minutes) / total_minutes) * 100, 4) if total_minutes else 0
        met = availability >= target_percent
        return {
            "message": "Reviewed SLO attainment",
            "target_percent": target_percent,
            "actual_percent": availability,
            "met_slo": met,
            "error_budget_remaining_minutes": round((total_minutes * (100 - target_percent) / 100) - downtime_minutes, 2),
        }
