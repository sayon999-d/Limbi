

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from agents import BaseAgent

class OSAgent(BaseAgent):

    agent_name = "os_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "operating_system",
            "status": "ready",
            "platform": platform.platform(),
            "capabilities": [
                "inspect_environment",
                "system_info",
                "disk_usage",
                "list_processes",
                "recommend_command",
            ],
        }

    def handle_inspect_environment(self, include_vars: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        include_vars = include_vars or ["PATH", "HOME", "SHELL", "USER", "PWD"]
        env = {name: os.getenv(name, "") for name in include_vars}
        return {
            "message": "Environment inspected",
            "variables": env,
            "cwd": str(Path.cwd()),
            "pythonpath_set": bool(os.getenv("PYTHONPATH")),
        }

    def handle_system_info(self, **kw: Any) -> dict[str, Any]:
        return {
            "message": "System information collected",
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "processor": platform.processor(),
        }

    def handle_disk_usage(self, path: str = ".", **kw: Any) -> dict[str, Any]:
        usage = shutil.disk_usage(path)
        return {
            "message": f"Disk usage calculated for {path}",
            "path": str(Path(path).resolve()),
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "used_percent": round((usage.used / usage.total) * 100, 2) if usage.total else 0,
        }

    def handle_list_processes(self, limit: int = 20, **kw: Any) -> dict[str, Any]:
        try:
            proc = subprocess.run(
                ["ps", "-axo", "pid,comm,%cpu,%mem"],
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception as exc:
            return {"message": "Unable to list processes", "error": str(exc), "processes": []}

        lines = [line.strip() for line in proc.stdout.splitlines()[1:] if line.strip()]
        processes = []
        for line in lines[:limit]:
            parts = line.split(None, 3)
            if len(parts) == 4:
                processes.append({
                    "pid": parts[0],
                    "command": parts[1],
                    "cpu_percent": parts[2],
                    "mem_percent": parts[3],
                })

        return {"message": f"Listed {len(processes)} processes", "processes": processes}

    def handle_recommend_command(self, objective: str = "", shell: str = "zsh", **kw: Any) -> dict[str, Any]:
        if not objective:
            raise ValueError("An 'objective' is required")

        objective_lower = objective.lower()
        if "disk" in objective_lower or "space" in objective_lower:
            command = "df -h"
        elif "process" in objective_lower or "cpu" in objective_lower:
            command = "ps -axo pid,comm,%cpu,%mem"
        elif "network" in objective_lower or "port" in objective_lower:
            command = "lsof -i -P"
        elif "files" in objective_lower or "find" in objective_lower:
            command = "rg --files"
        else:
            command = "pwd"

        return {
            "message": "Recommended a shell command",
            "objective": objective,
            "shell": shell,
            "recommended_command": command,
            "note": "Recommendation only; command not executed by this action",
        }
