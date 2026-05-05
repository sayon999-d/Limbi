

from __future__ import annotations

import ast
import json
import logging
import re
from typing import Any

from . import BaseAgent

logger = logging.getLogger("limbi.agents.critic")

class CriticAgent(BaseAgent):

    agent_name = "critic_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "evaluator_critic",
            "status": "ready",
            "capabilities": [
                "validate_json", "validate_code", "score_response",
                "check_hallucination", "validate_delegation",
            ],
        }

    def handle_validate_json(
        self,
        content: str = "",
        schema: dict[str, Any] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        issues: list[str] = []
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            return {
                "valid": False,
                "score": 0.0,
                "issues": [f"Invalid JSON: {e}"],
                "suggestion": "Fix the JSON syntax and retry",
            }

        if schema:
            required = schema.get("required", [])
            for field in required:
                if field not in parsed:
                    issues.append(f"Missing required field: '{field}'")

            properties = schema.get("properties", {})
            for field, spec in properties.items():
                if field in parsed:
                    expected_type = spec.get("type", "")
                    actual = type(parsed[field]).__name__
                    type_map = {"string": "str", "number": "float", "integer": "int", "boolean": "bool", "array": "list", "object": "dict"}
                    if expected_type and type_map.get(expected_type) != actual:
                        if not (expected_type == "number" and actual in ("int", "float")):
                            issues.append(f"Field '{field}' expected type '{expected_type}', got '{actual}'")

        score = max(0, 1.0 - len(issues) * 0.2)
        return {
            "valid": len(issues) == 0,
            "score": round(score, 2),
            "issues": issues,
            "parsed_keys": list(parsed.keys()) if isinstance(parsed, dict) else f"[{type(parsed).__name__}]",
        }

    def handle_validate_code(
        self,
        code: str = "",
        language: str = "python",
        **kw: Any,
    ) -> dict[str, Any]:

        issues: list[str] = []
        warnings: list[str] = []

        if language.lower() == "python":
            try:
                tree = ast.parse(code)

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        pass
                    if isinstance(node, ast.FunctionDef):
                        if not node.body:
                            warnings.append(f"Empty function: '{node.name}'")
                        if not node.name.islower() and not node.name.startswith("_"):
                            warnings.append(f"Function '{node.name}' doesn't follow snake_case convention")
                    if isinstance(node, ast.ClassDef):
                        if not any(c.isupper() for c in node.name):
                            warnings.append(f"Class '{node.name}' should use PascalCase")

            except SyntaxError as e:
                issues.append(f"Syntax error at line {e.lineno}: {e.msg}")

        elif language.lower() in ("javascript", "js", "typescript", "ts"):

            open_braces = code.count("{") - code.count("}")
            open_parens = code.count("(") - code.count(")")
            open_brackets = code.count("[") - code.count("]")

            if open_braces != 0:
                issues.append(f"Unbalanced braces: {'+' if open_braces > 0 else ''}{open_braces}")
            if open_parens != 0:
                issues.append(f"Unbalanced parentheses: {'+' if open_parens > 0 else ''}{open_parens}")
            if open_brackets != 0:
                issues.append(f"Unbalanced brackets: {'+' if open_brackets > 0 else ''}{open_brackets}")

            if "console.log" in code:
                warnings.append("Contains console.log statements (remove for production)")

        score = max(0, 1.0 - len(issues) * 0.3 - len(warnings) * 0.05)
        return {
            "valid": len(issues) == 0,
            "score": round(score, 2),
            "language": language,
            "issues": issues,
            "warnings": warnings,
            "line_count": len(code.strip().split("\n")),
        }

    def handle_score_response(
        self,
        response: str = "",
        criteria: list[str] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        criteria = criteria or ["completeness", "clarity", "actionability", "technical_depth"]
        scores: dict[str, float] = {}
        feedback: list[str] = []

        word_count = len(response.split())
        sentence_count = len(re.split(r'[.!?]+', response))
        has_code = "```" in response
        has_list = bool(re.search(r'^[\-\*\d]+\.?\s', response, re.MULTILINE))
        has_headers = bool(re.search(r'^#{1,3}\s', response, re.MULTILINE))

        if "completeness" in criteria:
            s = min(1.0, word_count / 50)
            if has_code: s = min(1.0, s + 0.2)
            if has_list: s = min(1.0, s + 0.1)
            scores["completeness"] = round(s, 2)
            if s < 0.5:
                feedback.append("Response is too brief - elaborate with examples or details")

        if "clarity" in criteria:
            avg_sentence_len = word_count / max(sentence_count, 1)
            s = max(0, 1.0 - abs(avg_sentence_len - 15) / 30)
            if has_headers: s = min(1.0, s + 0.15)
            scores["clarity"] = round(s, 2)
            if avg_sentence_len > 30:
                feedback.append("Sentences are too long - break them up for readability")

        if "actionability" in criteria:
            action_words = sum(1 for w in response.lower().split() if w in {
                "run", "execute", "deploy", "create", "install", "configure",
                "add", "update", "delete", "set", "use", "try", "check"
            })
            s = min(1.0, action_words / 5)
            if has_code: s = min(1.0, s + 0.3)
            scores["actionability"] = round(s, 2)
            if s < 0.3:
                feedback.append("Response lacks concrete action steps - add commands or code examples")

        if "technical_depth" in criteria:
            tech_indicators = sum(1 for pattern in [
                r'\b(API|SDK|CLI|HTTP|REST|SQL|DNS)\b',
                r'`[^`]+`',
                r'```',
                r'\b(function|class|import|const|var|let)\b',
            ] if re.search(pattern, response))
            s = min(1.0, tech_indicators / 3)
            scores["technical_depth"] = round(s, 2)

        overall = sum(scores.values()) / max(len(scores), 1)
        verdict = "excellent" if overall > 0.8 else "good" if overall > 0.6 else "needs_improvement" if overall > 0.4 else "poor"

        return {
            "overall_score": round(overall, 2),
            "verdict": verdict,
            "scores": scores,
            "feedback": feedback,
            "pass": overall >= 0.5,
            "meta": {"word_count": word_count, "has_code": has_code, "has_structure": has_headers or has_list},
        }

    def handle_check_hallucination(
        self,
        response: str = "",
        grounding_context: str = "",
        **kw: Any,
    ) -> dict[str, Any]:

        red_flags: list[str] = []
        suspicious_patterns = [
            (r'\b(always|never|guaranteed|impossible|certainly|definitely)\b', "Uses absolutist language"),
            (r'\b(studies show|research proves|experts agree)\b', "Makes unverifiable authority claims"),
            (r'\b(version \d+\.\d+\.\d+)\b', "Cites specific version numbers (verify!)"),
            (r'https?://\S+', "Contains URLs (which may be fabricated)"),
            (r'\b(published|released|announced) (?:on|in) \d{4}\b', "Cites specific dates"),
        ]

        for pattern, description in suspicious_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            if matches:
                red_flags.append(f"{description}: {matches[:3]}")

        grounding_score = 1.0
        ungrounded_claims: list[str] = []

        if grounding_context:

            sentences = re.split(r'[.!?]+', response)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence or len(sentence) < 20:
                    continue

                key_words = [w for w in sentence.split() if len(w) > 4 and w[0].isupper()]
                if key_words:
                    found = sum(1 for w in key_words if w.lower() in grounding_context.lower())
                    if found < len(key_words) * 0.3:
                        ungrounded_claims.append(sentence[:100])
                        grounding_score -= 0.1

        grounding_score = max(0, grounding_score)
        risk = "low" if len(red_flags) < 2 and grounding_score > 0.7 else "medium" if grounding_score > 0.4 else "high"

        return {
            "hallucination_risk": risk,
            "grounding_score": round(grounding_score, 2),
            "red_flags": red_flags,
            "ungrounded_claims": ungrounded_claims[:5],
            "recommendation": "Pass" if risk == "low" else "Review flagged items" if risk == "medium" else "Regenerate with better grounding",
        }

    def handle_validate_delegation(
        self,
        delegation: dict[str, Any] | None = None,
        available_agents: list[str] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        if not delegation:
            return {"valid": False, "issues": ["No delegation provided"]}

        issues: list[str] = []

        if "agent" not in delegation:
            issues.append("Missing 'agent' field")
        elif available_agents and delegation["agent"] not in available_agents:
            issues.append(f"Unknown agent: '{delegation['agent']}'. Available: {available_agents}")

        if "action" not in delegation:
            issues.append("Missing 'action' field")

        params = delegation.get("params", {})
        if not isinstance(params, dict):
            issues.append(f"'params' must be a dict, got {type(params).__name__}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "delegation": delegation,
        }
