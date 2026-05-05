from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.analytics")

_dashboards: dict[str, dict[str, Any]] = {}
_reports: list[dict[str, Any]] = []


class AnalyticsAgent(BaseAgent):

    agent_name = "analytics_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "analytics",
            "status": "ready",
            "dashboards": len(_dashboards),
            "reports_generated": len(_reports),
            "capabilities": [
                "create_dashboard",
                "funnel_analysis",
                "cohort_analysis",
                "generate_kpi_report",
                "anomaly_detection",
            ],
        }

    def handle_create_dashboard(
        self,
        name: str = "",
        metrics: list[str] | None = None,
        time_range: str = "7d",
        refresh_interval: str = "5m",
        **kw: Any,
    ) -> dict[str, Any]:
        if not name:
            raise ValueError("A dashboard 'name' is required")

        dashboard_id = str(uuid.uuid4())[:8]
        metrics = metrics or ["page_views", "conversions", "revenue"]
        dashboard = {
            "id": dashboard_id,
            "name": name,
            "metrics": metrics,
            "time_range": time_range,
            "refresh_interval": refresh_interval,
            "widgets": [
                {"type": "line_chart", "metric": m, "title": m.replace("_", " ").title()}
                for m in metrics
            ],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _dashboards[dashboard_id] = dashboard
        return {
            "message": f"Dashboard '{name}' created with {len(metrics)} metrics",
            "dashboard": dashboard,
        }

    def handle_funnel_analysis(
        self,
        funnel_name: str = "",
        steps: list[str] | None = None,
        total_users: int = 10000,
        **kw: Any,
    ) -> dict[str, Any]:
        if not funnel_name:
            raise ValueError("A 'funnel_name' is required")

        steps = steps or ["visit", "signup", "activate", "purchase"]
        drop_rates = [1.0, 0.45, 0.28, 0.12]
        analysis = []
        for i, step in enumerate(steps):
            rate = drop_rates[i] if i < len(drop_rates) else drop_rates[-1] * 0.5
            users = int(total_users * rate)
            analysis.append({
                "step": step,
                "users": users,
                "conversion_rate": f"{rate * 100:.1f}%",
                "drop_off": f"{(1 - rate) * 100:.1f}%" if i > 0 else "0%",
            })

        return {
            "message": f"Funnel '{funnel_name}' analyzed across {len(steps)} steps",
            "funnel": funnel_name,
            "steps": analysis,
            "overall_conversion": f"{drop_rates[-1] * 100:.1f}%",
            "biggest_drop": steps[1] if len(steps) > 1 else steps[0],
        }

    def handle_cohort_analysis(
        self,
        cohort_type: str = "weekly",
        periods: int = 8,
        metric: str = "retention",
        **kw: Any,
    ) -> dict[str, Any]:
        import random

        random.seed(42)
        cohorts = []
        for i in range(periods):
            retention = [100.0]
            for j in range(1, periods - i):
                prev = retention[-1]
                retention.append(round(prev * random.uniform(0.65, 0.90), 1))
            cohorts.append({
                "cohort": f"Period {i + 1}",
                "initial_users": random.randint(500, 2000),
                "retention_curve": retention,
            })

        return {
            "message": f"{cohort_type.title()} cohort analysis over {periods} periods",
            "cohort_type": cohort_type,
            "metric": metric,
            "cohorts": cohorts,
            "avg_retention_period_1": f"{sum(c['retention_curve'][1] for c in cohorts if len(c['retention_curve']) > 1) / max(len([c for c in cohorts if len(c['retention_curve']) > 1]), 1):.1f}%",
        }

    def handle_generate_kpi_report(
        self,
        department: str = "engineering",
        period: str = "monthly",
        kpis: list[str] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:
        kpi_templates = {
            "engineering": ["deployment_frequency", "lead_time", "mttr", "change_failure_rate", "velocity"],
            "sales": ["mrr", "arr", "churn_rate", "ltv", "cac", "pipeline_value"],
            "marketing": ["cpl", "cpa", "roas", "organic_traffic", "conversion_rate"],
            "product": ["dau", "mau", "feature_adoption", "nps", "time_to_value"],
        }
        selected_kpis = kpis or kpi_templates.get(department, kpi_templates["engineering"])
        report_id = str(uuid.uuid4())[:8]
        report = {
            "id": report_id,
            "department": department,
            "period": period,
            "kpis": [
                {"name": k, "current": "—", "target": "—", "status": "needs_data"}
                for k in selected_kpis
            ],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _reports.append(report)
        return {
            "message": f"KPI report for {department} ({period}) with {len(selected_kpis)} metrics",
            "report": report,
        }

    def handle_anomaly_detection(
        self,
        metric_name: str = "",
        values: list[float] | None = None,
        threshold_sigma: float = 2.0,
        **kw: Any,
    ) -> dict[str, Any]:
        if not metric_name:
            raise ValueError("'metric_name' is required")

        values = values or [100, 102, 98, 105, 97, 250, 101, 99]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std_dev = variance ** 0.5
        anomalies = [
            {"index": i, "value": v, "z_score": round((v - mean) / std_dev, 2)}
            for i, v in enumerate(values)
            if abs(v - mean) > threshold_sigma * std_dev
        ]

        return {
            "message": f"Anomaly detection on '{metric_name}': {len(anomalies)} anomalies found",
            "metric": metric_name,
            "mean": round(mean, 2),
            "std_dev": round(std_dev, 2),
            "threshold_sigma": threshold_sigma,
            "anomalies": anomalies,
            "data_points": len(values),
        }
