from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class ExecutionBackendProfile:
    name: str
    label: str
    kind: str
    idle_timeout_minutes: int
    supports_terminal: bool
    supports_hibernation: bool
    description: str


_BACKENDS = {
    "local": ExecutionBackendProfile(
        name="local",
        label="Local machine",
        kind="local",
        idle_timeout_minutes=30,
        supports_terminal=True,
        supports_hibernation=False,
        description="Run directly on the current workstation.",
    ),
    "docker": ExecutionBackendProfile(
        name="docker",
        label="Docker container",
        kind="container",
        idle_timeout_minutes=60,
        supports_terminal=True,
        supports_hibernation=True,
        description="Run inside a container with isolated filesystem and dependencies.",
    ),
    "ssh": ExecutionBackendProfile(
        name="ssh",
        label="Remote SSH host",
        kind="remote",
        idle_timeout_minutes=45,
        supports_terminal=True,
        supports_hibernation=True,
        description="Run on a remote Linux host reached over SSH.",
    ),
    "singularity": ExecutionBackendProfile(
        name="singularity",
        label="Singularity / Apptainer",
        kind="container",
        idle_timeout_minutes=60,
        supports_terminal=True,
        supports_hibernation=True,
        description="Portable HPC-friendly container backend.",
    ),
    "modal": ExecutionBackendProfile(
        name="modal",
        label="Modal serverless",
        kind="serverless",
        idle_timeout_minutes=5,
        supports_terminal=False,
        supports_hibernation=True,
        description="Ephemeral serverless execution for bursty workloads.",
    ),
    "daytona": ExecutionBackendProfile(
        name="daytona",
        label="Daytona workspace",
        kind="workspace",
        idle_timeout_minutes=20,
        supports_terminal=True,
        supports_hibernation=True,
        description="Remote developer workspace backend.",
    ),
    "vercel_sandbox": ExecutionBackendProfile(
        name="vercel_sandbox",
        label="Vercel Sandbox",
        kind="sandbox",
        idle_timeout_minutes=10,
        supports_terminal=False,
        supports_hibernation=True,
        description="Ephemeral sandbox for isolated execution.",
    ),
}


def list_execution_backends() -> list[dict[str, Any]]:
    return [asdict(profile) for profile in _BACKENDS.values()]


def get_execution_backend(name: str) -> dict[str, Any]:
    profile = _BACKENDS.get((name or "").strip().lower())
    return asdict(profile) if profile else {}


def recommend_execution_backend(task_text: str) -> dict[str, Any]:
    text = (task_text or "").lower()
    if any(token in text for token in ("deploy", "run in docker", "container", "image")):
        return asdict(_BACKENDS["docker"])
    if any(token in text for token in ("ssh", "remote host", "server")):
        return asdict(_BACKENDS["ssh"])
    if any(token in text for token in ("serverless", "scale", "burst", "modal")):
        return asdict(_BACKENDS["modal"])
    if any(token in text for token in ("gpu", "cluster", "hpc", "singularity")):
        return asdict(_BACKENDS["singularity"])
    return asdict(_BACKENDS["local"])


def build_backend_plan(task_text: str, backend_name: str = "") -> dict[str, Any]:
    backend = get_execution_backend(backend_name) if backend_name else recommend_execution_backend(task_text)
    return {
        "backend": backend,
        "workflow": [
            "prepare workspace",
            "run isolated task",
            "capture artifacts",
            "hibernate or teardown if idle",
        ],
        "idle_policy": {
            "supports_hibernation": backend.get("supports_hibernation", False),
            "idle_timeout_minutes": backend.get("idle_timeout_minutes", 0),
        },
        "message": f"Backend plan built for {backend.get('name') or 'local'}",
    }

