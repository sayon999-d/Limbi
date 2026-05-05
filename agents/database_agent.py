

from __future__ import annotations

import logging
import re
import time
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.database")

class DatabaseAgent(BaseAgent):

    agent_name = "database_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "database",
            "status": "ready",
            "capabilities": [
                "analyze_schema", "optimize_query",
                "generate_migration", "check_health",
                "generate_erd",
            ],
        }

    def handle_analyze_schema(
        self,
        tables: list[dict[str, Any]] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        tables = tables or []
        issues: list[dict[str, str]] = []
        suggestions: list[str] = []

        for table in tables:
            name = table.get("name", "")
            columns = table.get("columns", [])
            indexes = table.get("indexes", [])
            fks = table.get("foreign_keys", [])

            has_pk = any(c.get("primary_key") for c in columns)
            if not has_pk:
                issues.append({"table": name, "issue": "Missing primary key", "severity": "high"})

            indexed_cols = set()
            for idx in indexes:
                for col in idx.get("columns", []):
                    indexed_cols.add(col)

            for fk in fks:
                fk_col = fk.get("column", "")
                if fk_col and fk_col not in indexed_cols:
                    issues.append({
                        "table": name,
                        "issue": f"Foreign key '{fk_col}' lacks an index",
                        "severity": "medium",
                    })

            if len(columns) > 20:
                suggestions.append(f"Table '{name}' has {len(columns)} columns - consider normalization")

            if name != name.lower():
                suggestions.append(f"Table '{name}' - prefer snake_case naming")

        return {
            "message": f"Analyzed {len(tables)} tables: {len(issues)} issues found",
            "total_tables": len(tables),
            "total_columns": sum(len(t.get("columns", [])) for t in tables),
            "issues": issues,
            "suggestions": suggestions,
            "schema_score": max(0, 100 - len(issues) * 15 - len(suggestions) * 5),
        }

    def handle_optimize_query(
        self,
        query: str = "",
        dialect: str = "postgresql",
        **kw: Any,
    ) -> dict[str, Any]:

        if not query:
            raise ValueError("A SQL 'query' is required")

        suggestions: list[dict[str, str]] = []
        query_upper = query.upper()

        if "SELECT *" in query_upper:
            suggestions.append({
                "type": "performance",
                "issue": "SELECT * fetches all columns",
                "fix": "Specify only needed columns",
                "impact": "high",
            })

        if ("UPDATE " in query_upper or "DELETE " in query_upper) and "WHERE" not in query_upper:
            suggestions.append({
                "type": "safety",
                "issue": "UPDATE/DELETE without WHERE clause",
                "fix": "Add a WHERE clause to prevent full-table modification",
                "impact": "critical",
            })

        if re.search(r"LIKE\s+'%", query, re.I):
            suggestions.append({
                "type": "performance",
                "issue": "LIKE with leading wildcard prevents index usage",
                "fix": "Use full-text search or restructure the query",
                "impact": "high",
            })

        subquery_count = query_upper.count("SELECT") - 1
        if subquery_count > 0:
            suggestions.append({
                "type": "performance",
                "issue": f"{subquery_count} subquery(ies) detected",
                "fix": "Consider converting correlated subqueries to JOINs",
                "impact": "medium",
            })

        if "ORDER BY" in query_upper and "LIMIT" not in query_upper:
            suggestions.append({
                "type": "performance",
                "issue": "ORDER BY without LIMIT sorts entire result set",
                "fix": "Add LIMIT clause for paginated queries",
                "impact": "medium",
            })

        if query_upper.count("SELECT") > 2:
            suggestions.append({
                "type": "design",
                "issue": "Multiple nested SELECTs may indicate N+1 query pattern",
                "fix": "Use JOINs or batch queries",
                "impact": "high",
            })

        score = max(0, 100 - sum(
            30 if s["impact"] == "critical" else 20 if s["impact"] == "high" else 10
            for s in suggestions
        ))

        return {
            "message": f"Query analysis: {len(suggestions)} optimization(s) suggested",
            "query": query[:200],
            "dialect": dialect,
            "optimization_score": score,
            "suggestions": suggestions,
            "index_recommendations": self._suggest_indexes(query),
        }

    def handle_generate_migration(
        self,
        operation: str = "create_table",
        table_name: str = "",
        columns: list[dict[str, str]] | None = None,
        dialect: str = "postgresql",
        **kw: Any,
    ) -> dict[str, Any]:

        if not table_name:
            raise ValueError("'table_name' is required")

        columns = columns or []
        timestamp = time.strftime("%Y%m%d%H%M%S")

        up_sql = ""
        down_sql = ""

        if operation == "create_table":
            col_defs = []
            for col in columns:
                name = col.get("name", "id")
                dtype = col.get("type", "TEXT")
                constraints = col.get("constraints", "")
                col_defs.append(f"    {name} {dtype} {constraints}".rstrip())

            if not col_defs:
                col_defs = [
                    "    id SERIAL PRIMARY KEY",
                    "    created_at TIMESTAMP DEFAULT NOW()",
                    "    updated_at TIMESTAMP DEFAULT NOW()",
                ]

            up_sql = f"CREATE TABLE {table_name} (\n{','.join(chr(10) + c for c in col_defs)}\n);"
            down_sql = f"DROP TABLE IF EXISTS {table_name};"

        elif operation == "add_column":
            for col in columns:
                name = col.get("name", "")
                dtype = col.get("type", "TEXT")
                up_sql += f"ALTER TABLE {table_name} ADD COLUMN {name} {dtype};\n"
                down_sql += f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS {name};\n"

        elif operation == "add_index":
            for col in columns:
                name = col.get("name", "")
                idx_name = f"idx_{table_name}_{name}"
                up_sql += f"CREATE INDEX {idx_name} ON {table_name} ({name});\n"
                down_sql += f"DROP INDEX IF EXISTS {idx_name};\n"

        migration = {
            "filename": f"{timestamp}_{operation}_{table_name}.sql",
            "up": up_sql.strip(),
            "down": down_sql.strip(),
        }

        return {
            "message": f"Migration generated: {operation} on '{table_name}'",
            "migration": migration,
            "operation": operation,
            "table": table_name,
            "dialect": dialect,
        }

    def handle_check_health(
        self,
        db_type: str = "postgresql",
        connection_string: str = "",
        **kw: Any,
    ) -> dict[str, Any]:

        return {
            "message": f"[SIMULATED] Database health check ({db_type})",
            "db_type": db_type,
            "status": "healthy",
            "connection_pool": {"active": 5, "idle": 15, "max": 20},
            "latency_ms": 2.3,
            "replication_lag_ms": 0,
            "disk_usage_percent": 45.2,
            "slow_queries": 0,
            "note": "Provide connection_string for live health checks",
        }

    def handle_generate_erd(
        self,
        tables: list[dict[str, Any]] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        tables = tables or []

        mermaid = "erDiagram\n"
        for table in tables:
            name = table.get("name", "")
            columns = table.get("columns", [])

            for col in columns:
                col_name = col.get("name", "")
                col_type = col.get("type", "string")
                pk = " PK" if col.get("primary_key") else ""
                fk = " FK" if col.get("foreign_key") else ""
                mermaid += f'    {name} {{\n        {col_type} {col_name}{pk}{fk}\n    }}\n'

            for fk in table.get("foreign_keys", []):
                ref_table = fk.get("references", "")
                if ref_table:
                    mermaid += f'    {name} }}o--|| {ref_table} : "references"\n'

        return {
            "message": f"ERD generated for {len(tables)} tables",
            "mermaid": mermaid,
            "table_count": len(tables),
            "format": "mermaid",
        }

    def _suggest_indexes(self, query: str) -> list[str]:

        suggestions = []

        where_cols = re.findall(r'WHERE\s+(\w+)\s*[=<>]', query, re.I)
        for col in where_cols:
            suggestions.append(f"Consider index on column '{col}' (used in WHERE)")

        join_cols = re.findall(r'JOIN\s+\w+\s+(?:\w+\s+)?ON\s+\w+\.(\w+)', query, re.I)
        for col in join_cols:
            suggestions.append(f"Consider index on column '{col}' (used in JOIN)")

        order_cols = re.findall(r'ORDER BY\s+(\w+)', query, re.I)
        for col in order_cols:
            suggestions.append(f"Consider index on column '{col}' (used in ORDER BY)")

        return suggestions[:5]
