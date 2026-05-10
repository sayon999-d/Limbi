

from __future__ import annotations

import ast
import hashlib
import logging
import os
import subprocess
import tempfile
from typing import Any

from . import BaseAgent

logger = logging.getLogger("limbi.agents.code")

_TOOL_REGISTRY: dict[str, dict[str, Any]] = {}

class CodeAgent(BaseAgent):

    agent_name = "code_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "code_generation_tool_making",
            "status": "ready",
            "custom_tools": len(_TOOL_REGISTRY),
            "supported_languages": ["python", "javascript", "typescript", "go", "bash"],
        }

    def handle_generate_boilerplate(
        self,
        language: str = "python",
        template: str = "script",
        name: str = "untitled",
        description: str = "",
        **kw: Any,
    ) -> dict[str, Any]:

        templates = {
            ("python", "script"): _tmpl_python_script,
            ("python", "fastapi"): _tmpl_python_fastapi,
            ("python", "class"): _tmpl_python_class,
            ("python", "test"): _tmpl_python_test,
            ("python", "cli"): _tmpl_python_cli,
            ("bash", "script"): _tmpl_bash_script,
            ("", "dockerfile"): _tmpl_dockerfile,
            ("", "github_action"): _tmpl_github_action,
        }

        gen_func = templates.get((language.lower(), template.lower()))
        if not gen_func:
            gen_func = templates.get(("", template.lower()))
        if not gen_func:
            return {
                "message": f"Unknown template '{template}' for '{language}'",
                "available_templates": list({t for _, t in templates.keys()}),
                "available_languages": list({l for l, _ in templates.keys() if l}),
            }

        code = gen_func(name, description)
        return {
            "message": f"Generated {language} {template} boilerplate: '{name}'",
            "language": language,
            "template": template,
            "code": code,
            "line_count": len(code.strip().split("\n")),
        }

    def handle_validate_syntax(
        self,
        code: str = "",
        language: str = "python",
        **kw: Any,
    ) -> dict[str, Any]:

        if language.lower() == "python":
            try:
                ast.parse(code)
                return {"valid": True, "language": "python", "message": "Syntax is valid"}
            except SyntaxError as e:
                return {
                    "valid": False,
                    "language": "python",
                    "error": f"Line {e.lineno}: {e.msg}",
                    "line": e.lineno,
                }
        elif language.lower() in ("javascript", "js"):

            issues = []
            for char, name in [("{}", "braces"), ("()", "parens"), ("[]", "brackets")]:
                if code.count(char[0]) != code.count(char[1]):
                    issues.append(f"Unbalanced {name}")
            return {"valid": len(issues) == 0, "language": "javascript", "issues": issues}

        return {"valid": True, "language": language, "message": "No validator for this language (assumed valid)"}

    def handle_analyze_complexity(
        self,
        code: str = "",
        **kw: Any,
    ) -> dict[str, Any]:

        lines = code.strip().split("\n")
        total_lines = len(lines)
        blank_lines = sum(1 for l in lines if not l.strip())
        comment_lines = sum(1 for l in lines if l.strip().startswith("#") or l.strip().startswith("//"))
        code_lines = total_lines - blank_lines - comment_lines

        decision_keywords = sum(
            code.count(kw) for kw in [" if ", " elif ", " else:", " for ", " while ", " except ", " case ", " and ", " or "]
        )
        functions = len(re.findall(r'\bdef \w+|function \w+|const \w+ = ', code)) if 'import re' or True else 0
        import re as _re
        functions = len(_re.findall(r'\bdef \w+|function \w+|const \w+ =', code))

        complexity = "low" if decision_keywords < 5 else "medium" if decision_keywords < 15 else "high"

        return {
            "total_lines": total_lines,
            "code_lines": code_lines,
            "blank_lines": blank_lines,
            "comment_lines": comment_lines,
            "comment_ratio": round(comment_lines / max(code_lines, 1), 2),
            "functions_detected": functions,
            "decision_points": decision_keywords,
            "estimated_complexity": complexity,
        }

    def handle_create_tool(
        self,
        name: str = "",
        description: str = "",
        code: str = "",
        test_input: str = "",
        **kw: Any,
    ) -> dict[str, Any]:

        if not name or not code:
            raise ValueError("Both 'name' and 'code' are required")

        try:
            ast.parse(code)
        except SyntaxError as e:
            return {
                "success": False,
                "message": f"Tool code has syntax error at line {e.lineno}: {e.msg}",
            }

        tool_id = hashlib.sha256(f"{name}:{code}".encode()).hexdigest()[:12]
        _TOOL_REGISTRY[name] = {
            "id": tool_id,
            "name": name,
            "description": description,
            "code": code,
            "created": True,
            "tested": bool(test_input),
        }

        logger.info("Tool '%s' (id=%s) created and registered", name, tool_id)
        return {
            "message": f"Tool '{name}' created and registered",
            "tool_id": tool_id,
            "name": name,
            "description": description,
            "total_tools": len(_TOOL_REGISTRY),
        }

    def handle_write_to_file(
        self,
        path: str = "",
        content: str = "",
        language: str = "",
        overwrite: bool = True,
        **kw: Any,
    ) -> dict[str, Any]:
        if not path:
            raise ValueError("'path' is required")
        if not content:
            raise ValueError("'content' is required")

        from pathlib import Path as P
        target = P(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() and not overwrite:
            return {
                "message": f"File '{path}' already exists. Set overwrite=true to replace.",
                "written": False,
            }

        target.write_text(content, encoding="utf-8")

        return {
            "message": f"Wrote '{target.name}' ({len(content)} chars, {len(content.splitlines())} lines)",
            "written": True,
            "path": str(target),
            "language": language or target.suffix.lstrip("."),
            "lines": len(content.splitlines()),
        }

    def handle_list_tools(self, **kw: Any) -> dict[str, Any]:

        return {
            "tools": [
                {"name": t["name"], "id": t["id"], "description": t["description"]}
                for t in _TOOL_REGISTRY.values()
            ],
            "total": len(_TOOL_REGISTRY),
        }

    def handle_generate_test(
        self,
        function_name: str = "",
        function_code: str = "",
        framework: str = "pytest",
        **kw: Any,
    ) -> dict[str, Any]:

        if not function_name:
            return {"message": "Provide 'function_name' to generate tests for"}

        if framework == "pytest":
            test_code = f'''"""Tests for {function_name}"""
import pytest

class Test{function_name.title().replace("_", "")}:
    """Test suite for {function_name}."""

    def test_{function_name}_basic(self):
        """Test basic functionality."""
        result = {function_name}()
        assert result is not None

    def test_{function_name}_edge_case(self):
        """Test edge cases."""
        pass

    def test_{function_name}_error_handling(self):
        """Test error handling."""
        with pytest.raises(Exception):
            pass
'''
        else:
            test_code = f"Test stub for {function_name} - framework: {framework}"

        return {
            "message": f"Generated {framework} test for '{function_name}'",
            "code": test_code,
            "framework": framework,
        }

import re

def _tmpl_python_script(name: str, desc: str) -> str:
    return f'''#!/usr/bin/env python3
"""{desc or name}"""

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("{name}")

def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="{desc or name}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting {name}...")

    logger.info("Done.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
'''

def _tmpl_python_fastapi(name: str, desc: str) -> str:
    return f'''"""FastAPI service: {desc or name}"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="{name}", description="{desc}")

class ItemRequest(BaseModel):
    name: str
    value: float = 0.0

@app.get("/")
async def root():
    return {{"service": "{name}", "status": "ok"}}

@app.get("/health")
async def health():
    return {{"healthy": True}}

@app.post("/items")
async def create_item(req: ItemRequest):
    return {{"created": True, "item": req.model_dump()}}
'''

def _tmpl_python_class(name: str, desc: str) -> str:
    class_name = name.title().replace("_", "").replace("-", "")
    return f'''"""{desc or name}"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class {class_name}:
    """{desc or class_name}"""

    name: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def process(self) -> dict[str, Any]:
        """Process the data."""
        return {{"name": self.name, "processed": True}}

    def __repr__(self) -> str:
        return f"{class_name}(name={{self.name!r}})"
'''

def _tmpl_python_test(name: str, desc: str) -> str:
    return f'''"""Tests for {name}"""
import pytest

class Test{name.title().replace("_", "")}:
    """Test suite for {name}."""

    def setup_method(self):
        """Set up test fixtures."""
        pass

    def test_basic(self):
        """Test basic functionality."""
        assert True

    def test_edge_case(self):
        """Test edge cases."""
        pass

    @pytest.mark.parametrize("input_val,expected", [
        ("hello", True),
        ("", False),
    ])
    def test_parametrized(self, input_val, expected):
        """Parametrized tests."""
        assert bool(input_val) == expected
'''

def _tmpl_python_cli(name: str, desc: str) -> str:
    return f'''#!/usr/bin/env python3
"""{desc or name} - CLI tool"""
import click

@click.group()
@click.version_option("1.0.0")
def cli():
    """{desc or name}"""
    pass

@cli.command()
@click.argument("target")
@click.option("--verbose", "-v", is_flag=True)
def run(target: str, verbose: bool):
    """Run the main command."""
    if verbose:
        click.echo(f"Running on: {{target}}")
    click.echo(f" Done: {{target}}")

@cli.command()
def status():
    """Show status."""
    click.echo("Status: OK")

if __name__ == "__main__":
    cli()
'''

def _tmpl_bash_script(name: str, desc: str) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"

log() {{ echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"; }}

main() {{
    log "Starting {name}..."

    log "Done."
}}

main "$@"
'''

def _tmpl_dockerfile(name: str, desc: str) -> str:
    return f'''# {desc or name}
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /usr/local /usr/local
COPY . .

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
'''

def _tmpl_github_action(name: str, desc: str) -> str:
    return f'''name: {name}
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: pytest --tb=short -q
'''
