from __future__ import annotations

import logging
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.cicd")


class CICDAgent(BaseAgent):

    agent_name = "cicd_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "cicd", "status": "ready", "capabilities": ["generate_pipeline", "lint_pipeline", "deployment_strategy", "environment_matrix", "artifact_config"]}

    def handle_generate_pipeline(self, platform: str = "github_actions", language: str = "python", stages: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        stages = stages or ["lint", "test", "build", "deploy"]
        generators = {"github_actions": self._github_actions, "gitlab_ci": self._gitlab_ci}
        gen = generators.get(platform, self._github_actions)
        config = gen(language, stages)
        return {"message": f"CI/CD pipeline generated for {platform} ({language})", "platform": platform, "language": language, "stages": stages, "config": config}

    def handle_lint_pipeline(self, config: str = "", platform: str = "github_actions", **kw: Any) -> dict[str, Any]:
        if not config:
            raise ValueError("'config' is required")
        issues: list[str] = []
        if "secrets." not in config and ("API_KEY" in config or "TOKEN" in config):
            issues.append("Hardcoded secrets detected — use secrets manager")
        if "cache" not in config.lower():
            issues.append("No caching configured — add dependency caching for faster builds")
        if "timeout" not in config.lower():
            issues.append("No timeout set — add timeout to prevent hung jobs")
        return {"message": f"Pipeline lint: {len(issues)} issues found", "issues": issues, "status": "pass" if not issues else "warnings"}

    def handle_deployment_strategy(self, strategy: str = "rolling", instances: int = 3, **kw: Any) -> dict[str, Any]:
        strategies = {
            "rolling": {"description": "Gradually replace instances", "max_unavailable": 1, "max_surge": 1, "zero_downtime": True, "rollback_speed": "fast"},
            "blue_green": {"description": "Full parallel environment switch", "max_unavailable": 0, "max_surge": instances, "zero_downtime": True, "rollback_speed": "instant"},
            "canary": {"description": "Route small traffic % to new version", "canary_weight": "10%", "promotion_criteria": "error_rate < 1%", "zero_downtime": True, "rollback_speed": "instant"},
            "recreate": {"description": "Stop old, start new", "max_unavailable": instances, "zero_downtime": False, "rollback_speed": "slow"},
        }
        config = strategies.get(strategy, strategies["rolling"])
        return {"message": f"Deployment strategy: {strategy}", "strategy": strategy, "config": config, "instances": instances}

    def handle_environment_matrix(self, environments: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        environments = environments or ["dev", "staging", "production"]
        matrix = []
        for env in environments:
            matrix.append({"name": env, "auto_deploy": env == "dev", "requires_approval": env == "production", "branch": "main" if env == "production" else env, "tests": "full" if env != "dev" else "smoke"})
        return {"message": f"Environment matrix for {len(environments)} environments", "environments": matrix}

    def handle_artifact_config(self, artifact_type: str = "docker", registry: str = "", tag_strategy: str = "semver", **kw: Any) -> dict[str, Any]:
        configs = {
            "docker": {"registry": registry or "ghcr.io", "tag_strategy": tag_strategy, "multi_arch": True, "scan": True},
            "npm": {"registry": registry or "registry.npmjs.org", "tag_strategy": tag_strategy, "provenance": True},
            "pypi": {"registry": registry or "pypi.org", "tag_strategy": tag_strategy, "wheel": True, "sdist": True},
        }
        config = configs.get(artifact_type, configs["docker"])
        return {"message": f"Artifact config for {artifact_type}", "artifact_type": artifact_type, "config": config}

    def _github_actions(self, language: str, stages: list[str]) -> str:
        return f"""name: CI/CD
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
jobs:
  pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
{'      - run: ruff check .' if 'lint' in stages else ''}
{'      - run: pytest --tb=short' if 'test' in stages else ''}"""

    def _gitlab_ci(self, language: str, stages: list[str]) -> str:
        stage_list = "\n  ".join(f"- {s}" for s in stages)
        return f"""stages:\n  {stage_list}\n\ntest:\n  stage: test\n  image: python:3.12\n  script:\n    - pip install -r requirements.txt\n    - pytest"""
