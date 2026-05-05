from __future__ import annotations

import logging
import os
from typing import Any

from . import BaseAgent

logger = logging.getLogger("limbi.agents.azure")


class AzureAgent(BaseAgent):

    agent_name = "azure_agent"

    def __init__(self) -> None:
        self._configured = bool(os.getenv("AZURE_SUBSCRIPTION_ID") and os.getenv("AZURE_TENANT_ID"))
        self._subscription = os.getenv("AZURE_SUBSCRIPTION_ID", "")
        self._region = os.getenv("AZURE_REGION", "eastus")

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "azure", "status": "ready" if self._configured else "unconfigured", "region": self._region}

    def handle_list_resource_groups(self, **kw: Any) -> dict[str, Any]:
        return {"message": "[SIMULATED] Azure resource groups", "resource_groups": [{"name": "limbi-prod-rg", "location": self._region}], "count": 1}

    def handle_list_app_services(self, resource_group: str = "", **kw: Any) -> dict[str, Any]:
        return {"message": f"[SIMULATED] App Services in {resource_group or 'limbi-prod-rg'}", "app_services": [{"name": "limbi-api", "state": "Running"}], "count": 1}

    def handle_deploy_container_app(self, name: str = "", image: str = "", resource_group: str = "", cpu: float = 0.5, memory: str = "1Gi", **kw: Any) -> dict[str, Any]:
        if not name or not image:
            raise ValueError("Both 'name' and 'image' are required")
        return {"message": f"[SIMULATED] Container App '{name}' deploying", "name": name, "image": image, "url": f"https://{name}.azurecontainerapps.io"}

    def handle_get_aks_clusters(self, resource_group: str = "", **kw: Any) -> dict[str, Any]:
        return {"message": "[SIMULATED] AKS clusters", "clusters": [{"name": "limbi-aks", "status": "Running", "node_count": 3}], "count": 1}

    def handle_list_storage_accounts(self, **kw: Any) -> dict[str, Any]:
        return {"message": "[SIMULATED] Azure Storage accounts", "accounts": [{"name": "limbistorage", "kind": "StorageV2"}], "count": 1}
