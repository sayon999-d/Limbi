

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("limbi.parser")

_JSON_BLOCK_RE = re.compile(
    r"```json\s*\n(.*?)\n\s*```",
    re.DOTALL | re.IGNORECASE,
)

@dataclass
class ParsedOutput:

    conversation_text: str = ""
    delegation_payloads: list[dict[str, Any]] = field(default_factory=list)
    raw_json_blocks: list[str] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)

    @property
    def has_delegations(self) -> bool:
        return len(self.delegation_payloads) > 0

    def to_dict(self) -> dict:
        return {
            "conversation_text": self.conversation_text,
            "delegation_payloads": self.delegation_payloads,
            "raw_json_blocks": self.raw_json_blocks,
            "parse_errors": self.parse_errors,
            "has_delegations": self.has_delegations,
        }

def parse_llm_output(raw: str) -> ParsedOutput:

    result = ParsedOutput()

    matches: list[re.Match] = list(_JSON_BLOCK_RE.finditer(raw))

    for match in matches:
        json_str = match.group(1).strip()
        result.raw_json_blocks.append(json_str)
        try:
            parsed = json.loads(json_str)

            if isinstance(parsed, list):
                for item in parsed:
                    _validate_delegation(item)
                result.delegation_payloads.extend(parsed)
            elif isinstance(parsed, dict):
                _validate_delegation(parsed)
                result.delegation_payloads.append(parsed)
            else:
                result.parse_errors.append(
                    f"Unexpected JSON type: {type(parsed).__name__}"
                )
        except json.JSONDecodeError as exc:
            logger.warning("JSON parse error: %s", exc)
            result.parse_errors.append(f"JSONDecodeError: {exc}")
        except ValueError as exc:
            logger.warning("Validation error: %s", exc)
            result.parse_errors.append(str(exc))

    text_parts: list[str] = []
    cursor = 0
    for match in matches:

        before = raw[cursor : match.start()].strip()
        if before:
            text_parts.append(before)
        cursor = match.end()

    trailing = raw[cursor:].strip()
    if trailing:
        text_parts.append(trailing)

    result.conversation_text = "\n\n".join(text_parts)

    logger.info(
        "Parsed LLM output - %d delegation(s), %d error(s), %d chars of text",
        len(result.delegation_payloads),
        len(result.parse_errors),
        len(result.conversation_text),
    )
    return result

_REQUIRED_DELEGATION_KEYS = {"agent", "action"}

def _validate_delegation(item: Any) -> None:

    if not isinstance(item, dict):
        raise ValueError(f"Delegation must be a dict, got {type(item).__name__}")
    missing = _REQUIRED_DELEGATION_KEYS - set(item.keys())
    if missing:
        raise ValueError(f"Delegation dict missing required keys: {missing}")

if __name__ == "__main__":
    sample = """
Here's what I'll do for you:

1. I'll deploy the `main` branch to staging.
2. I'll create a Jira ticket to track it.

```json
[
  {"agent": "devops_agent", "action": "deploy_branch", "params": {"branch": "main", "env": "staging"}},
  {"agent": "jira_agent", "action": "create_ticket", "params": {"title": "Deploy main to staging", "priority": "high"}}
]
```

Let me know if you want me to change the target environment!
"""
    result = parse_llm_output(sample)
    print("=== Conversational Text ===")
    print(result.conversation_text)
    print("\n=== Delegations ===")
    for d in result.delegation_payloads:
        print(f"  -> {d}")
    print(f"\nErrors: {result.parse_errors}")
