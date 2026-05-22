

from __future__ import annotations

import logging
import os
from typing import Any

from . import BaseAgent
from ..execution_backends import (
    build_backend_plan,
    get_execution_backend,
    list_execution_backends,
    recommend_execution_backend,
)

logger = logging.getLogger("limbi.agents.devops")

class DevOpsAgent(BaseAgent):
    agent_name = "devops_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "status": "ready",
            "vercel_configured": bool(os.getenv("VERCEL_TOKEN")),
            "aws_configured": bool(os.getenv("AWS_ACCESS_KEY_ID")),
            "backend_catalog": len(list_execution_backends()),
            "capabilities": [
                "deploy_branch",
                "rollback",
                "check_status",
                "list_environments",
                "run_pipeline",
                "list_backends",
                "select_backend",
                "recommend_backend",
                "build_backend_plan",
            ],
        }

    def handle_deploy_branch(
        self,
        branch: str = "main",
        env: str = "staging",
        **kwargs: Any,
    ) -> dict[str, Any]:

        logger.info("Deploying branch '%s' -> %s", branch, env)

        return {
            "message": f"Branch '{branch}' deployment to '{env}' initiated.",
            "branch": branch,
            "environment": env,
            "status": "deploying",
            "estimated_time_seconds": 120,
        }

    def handle_rollback(
        self,
        env: str = "staging",
        version: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:

        logger.info("Rolling back %s to version %s", env, version or "previous")
        return {
            "message": f"Rollback of '{env}' initiated.",
            "environment": env,
            "target_version": version or "previous",
            "status": "rolling_back",
        }

    def handle_check_status(
        self,
        env: str = "staging",
        **kwargs: Any,
    ) -> dict[str, Any]:

        return {
            "environment": env,
            "status": "healthy",
            "uptime": "72h 14m",
            "last_deploy": "2026-04-03T18:30:00Z",
        }

    def handle_list_environments(self, **kwargs: Any) -> dict[str, Any]:

        return {
            "environments": [
                {"name": "development", "status": "healthy", "url": "https://dev.example.com"},
                {"name": "staging", "status": "healthy", "url": "https://staging.example.com"},
                {"name": "production", "status": "healthy", "url": "https://example.com"},
            ]
        }

    def handle_run_pipeline(
        self,
        pipeline: str = "build-test-deploy",
        branch: str = "main",
        **kwargs: Any,
    ) -> dict[str, Any]:

        logger.info("Triggering pipeline '%s' on branch '%s'", pipeline, branch)
        return {
            "pipeline": pipeline,
            "branch": branch,
            "status": "triggered",
            "run_id": "run-20260404-001",
        }

    def handle_list_backends(self, **kwargs: Any) -> dict[str, Any]:
        return {"message": "Listed execution backends", "backends": list_execution_backends()}

    def handle_select_backend(self, backend: str = "", **kwargs: Any) -> dict[str, Any]:
        profile = get_execution_backend(backend)
        if not profile:
            raise ValueError(f"Unknown backend '{backend}'")
        return {"message": f"Selected backend '{profile['name']}'", "backend": profile}

    def handle_recommend_backend(self, task_text: str = "", **kwargs: Any) -> dict[str, Any]:
        return {"message": "Recommended backend", "backend": recommend_execution_backend(task_text)}

    def handle_build_backend_plan(self, task_text: str = "", backend: str = "", **kwargs: Any) -> dict[str, Any]:
        return build_backend_plan(task_text, backend_name=backend)
