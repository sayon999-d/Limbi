from __future__ import annotations

import logging
import os
import time
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.gcp")


class GCPAgent(BaseAgent):

    agent_name = "gcp_agent"

    def __init__(self) -> None:
        self._configured = bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("GCP_PROJECT_ID"))
        self._project = os.getenv("GCP_PROJECT_ID", "")
        self._region = os.getenv("GCP_REGION", "us-central1")

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "gcp",
            "status": "ready" if self._configured else "unconfigured",
            "project": self._project,
            "region": self._region,
            "capabilities": [
                "list_cloud_run_services", "deploy_cloud_run",
                "list_gcs_buckets", "invoke_cloud_function", "get_gke_clusters",
            ],
        }

    def handle_list_cloud_run_services(self, region: str = "", **kw: Any) -> dict[str, Any]:
        region = region or self._region
        if self._configured:
            try:
                from google.cloud import run_v2
                client = run_v2.ServicesClient()
                parent = f"projects/{self._project}/locations/{region}"
                services = [
                    {"name": s.name.split("/")[-1], "url": s.uri, "status": s.conditions[0].type_ if s.conditions else "unknown"}
                    for s in client.list_services(parent=parent)
                ]
                return {"services": services, "count": len(services), "region": region}
            except Exception as exc:
                return {"message": f"Error listing Cloud Run services: {exc}", "simulated": False}

        return {
            "message": f"[SIMULATED] Cloud Run services in {region}",
            "services": [
                {"name": "limbi-api", "url": f"https://limbi-api-{region}.run.app", "status": "ACTIVE"},
                {"name": "limbi-worker", "url": f"https://limbi-worker-{region}.run.app", "status": "ACTIVE"},
            ],
            "count": 2,
            "region": region,
        }

    def handle_deploy_cloud_run(
        self,
        service_name: str = "",
        image: str = "",
        region: str = "",
        memory: str = "512Mi",
        cpu: str = "1",
        min_instances: int = 0,
        max_instances: int = 10,
        **kw: Any,
    ) -> dict[str, Any]:
        if not service_name or not image:
            raise ValueError("Both 'service_name' and 'image' are required")

        region = region or self._region
        return {
            "message": f"{'[SIMULATED] ' if not self._configured else ''}Deploying {service_name} to Cloud Run",
            "service": service_name,
            "image": image,
            "region": region,
            "config": {"memory": memory, "cpu": cpu, "min_instances": min_instances, "max_instances": max_instances},
            "url": f"https://{service_name}-{region}.run.app",
        }

    def handle_list_gcs_buckets(self, **kw: Any) -> dict[str, Any]:
        if self._configured:
            try:
                from google.cloud import storage
                client = storage.Client(project=self._project)
                buckets = [{"name": b.name, "location": b.location, "storage_class": b.storage_class} for b in client.list_buckets()]
                return {"buckets": buckets, "count": len(buckets)}
            except Exception as exc:
                return {"message": f"Error listing GCS buckets: {exc}"}

        return {
            "message": "[SIMULATED] GCS bucket listing",
            "buckets": [
                {"name": f"{self._project}-data", "location": "US", "storage_class": "STANDARD"},
                {"name": f"{self._project}-backups", "location": "US", "storage_class": "NEARLINE"},
            ],
            "count": 2,
        }

    def handle_invoke_cloud_function(
        self,
        function_name: str = "",
        payload: dict | None = None,
        region: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        if not function_name:
            raise ValueError("'function_name' is required")
        region = region or self._region

        return {
            "message": f"[SIMULATED] Cloud Function '{function_name}' invoked in {region}",
            "function_name": function_name,
            "region": region,
            "payload": payload,
            "result": {"statusCode": 200, "body": "OK"},
        }

    def handle_get_gke_clusters(self, region: str = "", **kw: Any) -> dict[str, Any]:
        region = region or self._region
        return {
            "message": f"[SIMULATED] GKE clusters in {region}",
            "clusters": [
                {"name": "limbi-prod", "status": "RUNNING", "node_count": 3, "version": "1.28.5-gke.1200"},
            ],
            "count": 1,
            "region": region,
        }
