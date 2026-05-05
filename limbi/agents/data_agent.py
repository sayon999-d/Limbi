

from __future__ import annotations

import csv
import io
import json
import logging
import math
from collections import Counter, defaultdict
from typing import Any

from . import BaseAgent

logger = logging.getLogger("limbi.agents.data")

class DataAgent(BaseAgent):

    agent_name = "data_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "data_analysis",
            "status": "ready",
            "capabilities": [
                "analyze_csv", "analyze_json", "compute_stats",
                "detect_outliers", "transform_data",
            ],
        }

    def handle_analyze_csv(
        self,
        data: str = "",
        delimiter: str = ",",
        has_header: bool = True,
        **kw: Any,
    ) -> dict[str, Any]:

        if not data:
            raise ValueError("CSV 'data' string is required")

        reader = csv.reader(io.StringIO(data), delimiter=delimiter)
        rows = list(reader)

        if not rows:
            return {"message": "Empty CSV data", "rows": 0}

        headers = rows[0] if has_header else [f"col_{i}" for i in range(len(rows[0]))]
        data_rows = rows[1:] if has_header else rows

        columns: dict[str, dict[str, Any]] = {}
        for col_idx, header in enumerate(headers):
            values = [r[col_idx] for r in data_rows if col_idx < len(r)]
            non_empty = [v for v in values if v.strip()]

            numeric_count = sum(1 for v in non_empty if self._is_numeric(v))
            is_numeric = numeric_count > len(non_empty) * 0.8 and non_empty

            col_info: dict[str, Any] = {
                "name": header,
                "total_values": len(values),
                "non_empty": len(non_empty),
                "null_count": len(values) - len(non_empty),
                "unique_count": len(set(non_empty)),
                "type": "numeric" if is_numeric else "text",
            }

            if is_numeric:
                nums = [float(v) for v in non_empty if self._is_numeric(v)]
                if nums:
                    col_info["min"] = min(nums)
                    col_info["max"] = max(nums)
                    col_info["mean"] = round(sum(nums) / len(nums), 2)
                    col_info["median"] = round(self._median(nums), 2)
            else:

                top = Counter(non_empty).most_common(5)
                col_info["top_values"] = [{"value": v, "count": c} for v, c in top]

            columns[header] = col_info

        return {
            "message": f"Analyzed CSV: {len(data_rows)} rows  {len(headers)} columns",
            "rows": len(data_rows),
            "columns": len(headers),
            "schema": columns,
            "sample_rows": [dict(zip(headers, r)) for r in data_rows[:5]],
        }

    def handle_analyze_json(
        self,
        data: str = "",
        **kw: Any,
    ) -> dict[str, Any]:

        if not data:
            raise ValueError("JSON 'data' string is required")

        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as e:
            return {"valid": False, "error": f"Invalid JSON: {e}"}

        schema = self._infer_schema(parsed)
        depth = self._max_depth(parsed)

        result: dict[str, Any] = {
            "message": f"Analyzed JSON structure (depth={depth})",
            "valid": True,
            "root_type": type(parsed).__name__,
            "depth": depth,
            "schema": schema,
        }

        if isinstance(parsed, list):
            result["array_length"] = len(parsed)
            if parsed and isinstance(parsed[0], dict):
                result["sample_keys"] = list(parsed[0].keys())[:10]
        elif isinstance(parsed, dict):
            result["key_count"] = len(parsed)
            result["keys"] = list(parsed.keys())[:20]

        return result

    def handle_compute_stats(
        self,
        values: list[float | int] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        if not values:
            raise ValueError("A 'values' list of numbers is required")

        nums = [float(v) for v in values]
        n = len(nums)
        sorted_nums = sorted(nums)

        mean = sum(nums) / n
        variance = sum((x - mean) ** 2 for x in nums) / n
        std = math.sqrt(variance)
        median = self._median(nums)

        counts = Counter(nums)
        mode_val, mode_count = counts.most_common(1)[0]

        p25 = sorted_nums[int(n * 0.25)]
        p75 = sorted_nums[int(n * 0.75)]
        iqr = p75 - p25

        return {
            "message": f"Statistics for {n} values",
            "count": n,
            "mean": round(mean, 4),
            "median": round(median, 4),
            "mode": mode_val,
            "mode_frequency": mode_count,
            "std_dev": round(std, 4),
            "variance": round(variance, 4),
            "min": min(nums),
            "max": max(nums),
            "range": round(max(nums) - min(nums), 4),
            "sum": round(sum(nums), 4),
            "percentiles": {
                "p25": round(p25, 4),
                "p50": round(median, 4),
                "p75": round(p75, 4),
            },
            "iqr": round(iqr, 4),
            "skewness": round(self._skewness(nums, mean, std), 4) if std > 0 else 0,
        }

    def handle_detect_outliers(
        self,
        values: list[float | int] | None = None,
        method: str = "iqr",
        threshold: float = 1.5,
        **kw: Any,
    ) -> dict[str, Any]:

        if not values:
            raise ValueError("A 'values' list is required")

        nums = [float(v) for v in values]
        outliers: list[dict[str, Any]] = []

        if method == "zscore":
            mean = sum(nums) / len(nums)
            std = math.sqrt(sum((x - mean) ** 2 for x in nums) / len(nums))
            if std > 0:
                for i, v in enumerate(nums):
                    z = abs(v - mean) / std
                    if z > threshold:
                        outliers.append({"index": i, "value": v, "z_score": round(z, 2)})
        else:
            sorted_nums = sorted(nums)
            n = len(sorted_nums)
            q1 = sorted_nums[int(n * 0.25)]
            q3 = sorted_nums[int(n * 0.75)]
            iqr = q3 - q1
            lower = q1 - threshold * iqr
            upper = q3 + threshold * iqr

            for i, v in enumerate(nums):
                if v < lower or v > upper:
                    outliers.append({
                        "index": i, "value": v,
                        "direction": "below" if v < lower else "above",
                    })

        return {
            "message": f"Found {len(outliers)} outliers in {len(nums)} values using {method}",
            "total_values": len(nums),
            "outlier_count": len(outliers),
            "outlier_percentage": round(len(outliers) / max(len(nums), 1) * 100, 1),
            "outliers": outliers[:50],
            "method": method,
            "threshold": threshold,
        }

    def handle_transform_data(
        self,
        data: list[dict[str, Any]] | None = None,
        operations: list[dict[str, Any]] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        if not data:
            raise ValueError("A 'data' list of objects is required")

        result = list(data)
        applied: list[str] = []

        for op_spec in (operations or []):
            op = op_spec.get("op", "")
            field = op_spec.get("field", "")

            if op == "filter":
                cond = op_spec.get("condition", "eq")
                val = op_spec.get("value")
                result = [r for r in result if self._check_condition(r.get(field), cond, val)]
                applied.append(f"filter({field} {cond} {val})")

            elif op == "sort":
                order = op_spec.get("order", "asc")
                result.sort(key=lambda r: r.get(field, ""), reverse=(order == "desc"))
                applied.append(f"sort({field} {order})")

            elif op == "group_by":
                agg = op_spec.get("agg", "count")
                groups: dict[Any, list] = defaultdict(list)
                for r in result:
                    groups[r.get(field, "unknown")].append(r)

                if agg == "count":
                    result = [{"group": k, "count": len(v)} for k, v in groups.items()]
                elif agg == "sum":
                    agg_field = op_spec.get("agg_field", "")
                    result = [
                        {"group": k, "sum": sum(r.get(agg_field, 0) for r in v)}
                        for k, v in groups.items()
                    ]
                applied.append(f"group_by({field}, {agg})")

            elif op == "select":
                fields = op_spec.get("fields", [])
                result = [{f: r.get(f) for f in fields} for r in result]
                applied.append(f"select({', '.join(fields)})")

        return {
            "message": f"Applied {len(applied)} operations, {len(result)} rows remaining",
            "operations_applied": applied,
            "row_count": len(result),
            "data": result[:100],
            "truncated": len(result) > 100,
        }

    @staticmethod
    def _is_numeric(val: str) -> bool:
        try:
            float(val)
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _median(nums: list[float]) -> float:
        s = sorted(nums)
        n = len(s)
        if n % 2 == 0:
            return (s[n // 2 - 1] + s[n // 2]) / 2
        return s[n // 2]

    @staticmethod
    def _skewness(nums: list[float], mean: float, std: float) -> float:
        n = len(nums)
        return sum(((x - mean) / std) ** 3 for x in nums) / n

    @staticmethod
    def _check_condition(val: Any, cond: str, target: Any) -> bool:
        try:
            if cond == "eq":
                return val == target
            elif cond == "neq":
                return val != target
            elif cond == "gt":
                return float(val) > float(target)
            elif cond == "lt":
                return float(val) < float(target)
            elif cond == "gte":
                return float(val) >= float(target)
            elif cond == "lte":
                return float(val) <= float(target)
            elif cond == "contains":
                return str(target).lower() in str(val).lower()
        except (ValueError, TypeError):
            return False
        return True

    def _infer_schema(self, obj: Any, depth: int = 0) -> Any:
        if depth > 5:
            return "..."
        if isinstance(obj, dict):
            return {k: self._infer_schema(v, depth + 1) for k, v in list(obj.items())[:15]}
        elif isinstance(obj, list):
            if not obj:
                return "[]"
            return [self._infer_schema(obj[0], depth + 1)]
        else:
            return type(obj).__name__

    def _max_depth(self, obj: Any, d: int = 0) -> int:
        if isinstance(obj, dict):
            return max((self._max_depth(v, d + 1) for v in obj.values()), default=d)
        elif isinstance(obj, list):
            return max((self._max_depth(v, d + 1) for v in obj), default=d)
        return d
