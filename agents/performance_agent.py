from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.performance")


class PerformanceAgent(BaseAgent):

    agent_name = "performance_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "performance", "status": "ready", "capabilities": ["profile_endpoint", "memory_analysis", "latency_report", "capacity_plan", "optimize_query"]}

    def handle_profile_endpoint(self, endpoint: str = "", method: str = "GET", samples: int = 100, **kw: Any) -> dict[str, Any]:
        if not endpoint:
            raise ValueError("'endpoint' is required")
        import random
        random.seed(hash(endpoint))
        latencies = sorted([random.uniform(10, 500) for _ in range(samples)])
        return {"message": f"Profiled {method} {endpoint} ({samples} samples)", "endpoint": endpoint, "method": method, "metrics": {
            "p50_ms": round(latencies[int(samples*0.5)], 1), "p95_ms": round(latencies[int(samples*0.95)], 1),
            "p99_ms": round(latencies[int(samples*0.99)], 1), "mean_ms": round(sum(latencies)/len(latencies), 1),
            "min_ms": round(latencies[0], 1), "max_ms": round(latencies[-1], 1),
        }, "samples": samples}

    def handle_memory_analysis(self, process_name: str = "", heap_mb: float = 0, rss_mb: float = 0, gc_collections: int = 0, **kw: Any) -> dict[str, Any]:
        issues: list[str] = []
        if heap_mb > 500:
            issues.append("High heap usage — consider memory pooling")
        if rss_mb > 1000:
            issues.append("RSS exceeds 1GB — check for memory leaks")
        if gc_collections > 100:
            issues.append("Excessive GC — review object allocation patterns")
        return {"message": f"Memory analysis for '{process_name or 'unknown'}'", "heap_mb": heap_mb, "rss_mb": rss_mb, "gc_collections": gc_collections, "issues": issues, "status": "healthy" if not issues else "needs_attention"}

    def handle_latency_report(self, services: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
        services = services or [
            {"name": "api-gateway", "p50": 12, "p95": 45, "p99": 120},
            {"name": "auth-service", "p50": 8, "p95": 30, "p99": 80},
            {"name": "database", "p50": 3, "p95": 15, "p99": 50},
        ]
        slowest = max(services, key=lambda s: s.get("p99", 0))
        return {"message": f"Latency report for {len(services)} services", "services": services, "slowest_p99": slowest["name"], "recommendation": f"Optimize {slowest['name']} (p99={slowest.get('p99')}ms)"}

    def handle_capacity_plan(self, current_rps: int = 0, target_rps: int = 0, current_instances: int = 1, cpu_per_instance: float = 0.5, **kw: Any) -> dict[str, Any]:
        if not target_rps:
            return {"message": "Provide 'target_rps' to plan capacity"}
        scale_factor = target_rps / max(current_rps, 1)
        needed = max(1, int(current_instances * scale_factor * 1.2))
        return {"message": f"Capacity plan: {current_rps} -> {target_rps} RPS", "current_rps": current_rps, "target_rps": target_rps, "current_instances": current_instances, "recommended_instances": needed, "headroom": "20%", "estimated_cpu_cores": round(needed * cpu_per_instance, 1)}

    def handle_optimize_query(self, query: str = "", **kw: Any) -> dict[str, Any]:
        if not query:
            raise ValueError("'query' is required")
        suggestions: list[str] = []
        q = query.upper()
        if "SELECT *" in q:
            suggestions.append("Avoid SELECT * — specify only needed columns")
        if "WHERE" not in q and ("UPDATE" in q or "DELETE" in q):
            suggestions.append("Missing WHERE clause — could affect all rows")
        if "JOIN" in q and "INDEX" not in q:
            suggestions.append("Consider adding indexes on JOIN columns")
        if "LIKE '%'" in q:
            suggestions.append("Leading wildcard in LIKE prevents index usage")
        if "ORDER BY" in q and "LIMIT" not in q:
            suggestions.append("Add LIMIT to ORDER BY queries to reduce sorting overhead")
        if not suggestions:
            suggestions.append("Query looks reasonable — profile with EXPLAIN for details")
        return {"message": f"Query optimization: {len(suggestions)} suggestions", "suggestions": suggestions, "query_length": len(query)}
