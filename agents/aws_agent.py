
from __future__ import annotations

import logging
import os
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.aws")

class AWSAgent(BaseAgent):
    agent_name = "aws_agent"

    def __init__(self) -> None:
        self._configured = bool(
            os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")
        )
        self._region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "status": "ready" if self._configured else "unconfigured",
            "region": self._region,
            "aws_configured": self._configured,
        }

    def handle_list_s3_buckets(self, **kwargs: Any) -> dict[str, Any]:

        if self._configured:
            import boto3

            s3 = boto3.client("s3", region_name=self._region)
            response = s3.list_buckets()
            buckets = [
                {"name": b["Name"], "created": b["CreationDate"].isoformat()}
                for b in response.get("Buckets", [])
            ]
            return {"buckets": buckets, "count": len(buckets)}

        return {
            "message": "[SIMULATED] S3 bucket listing",
            "buckets": [
                {"name": "limbi-data", "created": "2026-01-01T00:00:00Z"},
                {"name": "limbi-logs", "created": "2026-02-15T00:00:00Z"},
            ],
            "count": 2,
        }

    def handle_invoke_lambda(
        self,
        function_name: str = "",
        payload: dict | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not function_name:
            raise ValueError("'function_name' is required")
        logger.info("Invoking Lambda: %s", function_name)

        if self._configured:
            import json
            import boto3

            client = boto3.client("lambda", region_name=self._region)
            response = client.invoke(
                FunctionName=function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload or {}),
            )
            result = json.loads(response["Payload"].read())
            return {
                "message": f"Lambda '{function_name}' invoked",
                "status_code": response["StatusCode"],
                "result": result,
            }

        return {
            "message": f"[SIMULATED] Lambda '{function_name}' invoked",
            "function_name": function_name,
            "payload": payload,
            "status_code": 200,
            "result": {"statusCode": 200, "body": "OK"},
        }

    def handle_describe_instances(
        self,
        state: str = "running",
        **kwargs: Any,
    ) -> dict[str, Any]:
        if self._configured:
            import boto3

            ec2 = boto3.client("ec2", region_name=self._region)
            response = ec2.describe_instances(
                Filters=[{"Name": "instance-state-name", "Values": [state]}]
            )
            instances = []
            for reservation in response.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    instances.append({
                        "id": inst["InstanceId"],
                        "type": inst["InstanceType"],
                        "state": inst["State"]["Name"],
                    })
            return {"instances": instances, "count": len(instances)}

        return {
            "message": f"[SIMULATED] EC2 instances (state={state})",
            "instances": [
                {"id": "i-0abc123def", "type": "t3.medium", "state": state},
                {"id": "i-0def456ghi", "type": "t3.large", "state": state},
            ],
            "count": 2,
        }

    def handle_get_cloudwatch_metrics(
        self,
        namespace: str = "AWS/EC2",
        metric: str = "CPUUtilization",
        period_hours: int = 1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {
            "message": f"[SIMULATED] CloudWatch metrics for {namespace}/{metric}",
            "namespace": namespace,
            "metric": metric,
            "period_hours": period_hours,
            "average": 23.4,
            "max": 67.8,
            "min": 2.1,
        }
