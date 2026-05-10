from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import logging
import os
import re
import textwrap
import time
import uuid
from pathlib import Path
from typing import Any

from limbi.agents import BaseAgent, list_agents, _AGENT_REGISTRY

logger = logging.getLogger("limbi.agents.mutation")

_PROPOSALS: dict[str, dict[str, Any]] = {}

_CURRENT_PATTERN_VERSION = "2.0.0"

_AGENT_TEMPLATE = textwrap.dedent('''\
    from __future__ import annotations

    import logging
    from typing import Any

    from limbi.agents import BaseAgent

    logger = logging.getLogger("limbi.agents.{agent_name}")


    class {agent_class_name}(BaseAgent):

        agent_name = "{agent_name}"

        def health_check(self) -> dict[str, Any]:
            return {{
                "agent": self.agent_name,
                "type": "{agent_type}",
                "status": "ready",
                "capabilities": {capabilities},
                "pattern_version": "{pattern_version}",
                "auto_generated": True,
            }}

    {handler_methods}
''')

_HANDLER_TEMPLATE = textwrap.dedent('''\
        def handle_{action}(self, **kw: Any) -> dict[str, Any]:
            return {{
                "message": "{action} executed on {agent_name}",
                "params": kw,
                "status": "completed",
            }}
''')


def _agent_file_path(agent_name: str, package_root: str = "limbi/agents") -> Path:
    base = Path(__file__).resolve().parent
    return base / f"{agent_name}.py"


def _to_class_name(agent_name: str) -> str:
    return "".join(word.capitalize() for word in agent_name.split("_"))


class MutationAgent(BaseAgent):

    agent_name = "mutation_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "meta_self_mutation",
            "status": "ready",
            "capabilities": [
                "detect_missing",
                "propose_agent",
                "create_agent",
                "evolve_agent",
                "list_mutations",
                "rollback",
            ],
            "pattern_version": _CURRENT_PATTERN_VERSION,
            "pending_proposals": len(
                [p for p in _PROPOSALS.values() if p["status"] == "pending"]
            ),
        }

    def handle_detect_missing(
        self,
        task_description: str = "",
        required_agents: list[str] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:
        if not task_description and not required_agents:
            raise ValueError(
                "Provide 'task_description' or 'required_agents' to detect gaps"
            )

        registered = set(list_agents().keys())
        missing: list[str] = []

        if required_agents:
            missing = [a for a in required_agents if a not in registered]
        else:
            candidates = set(re.findall(r"[a-z_]+_agent", task_description.lower()))
            missing = [a for a in candidates if a not in registered]

        suggestions: list[dict[str, str]] = []
        for m in missing:
            suggestions.append({
                "agent": m,
                "class_name": _to_class_name(m),
                "recommendation": (
                    "Run mutation_agent.propose_agent to generate a scaffold, "
                    "then mutation_agent.create_agent with the approval token."
                ),
            })

        return {
            "message": (
                f"Found {len(missing)} missing agent(s)"
                if missing
                else "All required agents are registered"
            ),
            "registered_count": len(registered),
            "missing": missing,
            "suggestions": suggestions,
        }

    def handle_propose_agent(
        self,
        agent_name: str = "",
        purpose: str = "",
        actions: list[str] | None = None,
        agent_type: str = "general",
        **kw: Any,
    ) -> dict[str, Any]:
        if not agent_name:
            raise ValueError("'agent_name' is required (e.g. 'video_agent')")
        if not agent_name.endswith("_agent"):
            agent_name = f"{agent_name}_agent"

        if agent_name in list_agents():
            return {
                "message": f"Agent '{agent_name}' already exists -- use evolve_agent instead",
                "exists": True,
            }

        actions = actions or ["execute"]
        class_name = _to_class_name(agent_name)
        purpose = purpose or f"Handle {agent_type}-domain tasks"

        handler_blocks: list[str] = []
        for action in actions:
            handler_blocks.append(
                _HANDLER_TEMPLATE.format(action=action, agent_name=agent_name)
            )

        code = _AGENT_TEMPLATE.format(
            agent_class_name=class_name,
            agent_name=agent_name,
            agent_type=agent_type,
            purpose=purpose,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            pattern_version=_CURRENT_PATTERN_VERSION,
            capabilities=json.dumps(actions),
            handler_methods="\n".join(handler_blocks),
        )

        proposal_id = str(uuid.uuid4())[:8]
        approval_token = hashlib.sha256(
            f"{proposal_id}:{agent_name}:{time.time()}".encode()
        ).hexdigest()[:16]

        _PROPOSALS[proposal_id] = {
            "id": proposal_id,
            "agent_name": agent_name,
            "class_name": class_name,
            "purpose": purpose,
            "actions": actions,
            "code": code,
            "approval_token": approval_token,
            "status": "pending",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "applied_at": None,
        }

        return {
            "message": (
                f"Agent proposal '{agent_name}' ready for review. "
                f"Pass approval_token to create_agent to apply."
            ),
            "proposal_id": proposal_id,
            "approval_token": approval_token,
            "agent_name": agent_name,
            "class_name": class_name,
            "actions": actions,
            "code_preview": code,
            "requires_approval": True,
            "approval_instruction": (
                "To create this agent, call mutation_agent.create_agent "
                f"with approval_token='{approval_token}'"
            ),
        }

    def handle_create_agent(
        self,
        approval_token: str = "",
        proposal_id: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        if not approval_token:
            raise ValueError(
                "'approval_token' is required -- get it from propose_agent"
            )

        proposal = None
        for p in _PROPOSALS.values():
            if p["approval_token"] == approval_token:
                proposal = p
                break
        if proposal_id and proposal_id in _PROPOSALS:
            proposal = _PROPOSALS[proposal_id]

        if proposal is None:
            return {
                "message": "No matching proposal found for this approval token",
                "approved": False,
            }

        if proposal["status"] != "pending":
            return {
                "message": f"Proposal already {proposal['status']}",
                "approved": False,
            }

        if proposal["approval_token"] != approval_token:
            return {
                "message": "Approval token mismatch -- permission denied",
                "approved": False,
            }

        agent_name = proposal["agent_name"]
        code = proposal["code"]

        target = _agent_file_path(agent_name)
        written_paths: list[str] = []
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(code, encoding="utf-8")
            written_paths.append(str(target))

        root_agents = Path(__file__).resolve().parent.parent.parent / "agents"
        if root_agents.is_dir():
            root_target = root_agents / f"{agent_name}.py"
            if not root_target.exists():
                root_code = code.replace("from limbi.agents import", "from agents import")
                root_target.write_text(root_code, encoding="utf-8")
                written_paths.append(str(root_target))

        try:
            mod = importlib.import_module(f"limbi.agents.{agent_name}")
            importlib.reload(mod)
        except Exception as exc:
            logger.warning("Hot-load failed for %s: %s", agent_name, exc)

        proposal["status"] = "applied"
        proposal["applied_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        return {
            "message": f"Agent '{agent_name}' created and registered",
            "approved": True,
            "agent_name": agent_name,
            "files_written": written_paths,
            "hot_loaded": agent_name in list_agents(),
        }

    def handle_evolve_agent(
        self,
        agent_name: str = "",
        upgrade_actions: list[str] | None = None,
        approval_token: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        if not agent_name:
            raise ValueError("'agent_name' is required")
        if agent_name not in list_agents():
            return {
                "message": f"Agent '{agent_name}' not found -- use propose_agent instead",
                "exists": False,
            }

        current_actions = list_agents()[agent_name]
        new_actions = list(set(current_actions + (upgrade_actions or [])))

        source_path = _agent_file_path(agent_name)
        current_source = ""
        if source_path.exists():
            current_source = source_path.read_text(encoding="utf-8")

        version_match = re.search(r'pattern_version.*?["\'](\d+\.\d+\.\d+)["\']', current_source)
        current_version = version_match.group(1) if version_match else "1.0.0"

        if current_version == _CURRENT_PATTERN_VERSION and not upgrade_actions:
            return {
                "message": f"Agent '{agent_name}' is already at pattern v{_CURRENT_PATTERN_VERSION}",
                "current_version": current_version,
                "latest_version": _CURRENT_PATTERN_VERSION,
                "up_to_date": True,
            }

        if not approval_token:
            proposal_id = str(uuid.uuid4())[:8]
            token = hashlib.sha256(
                f"evolve:{proposal_id}:{agent_name}:{time.time()}".encode()
            ).hexdigest()[:16]

            _PROPOSALS[proposal_id] = {
                "id": proposal_id,
                "agent_name": agent_name,
                "type": "evolution",
                "current_version": current_version,
                "target_version": _CURRENT_PATTERN_VERSION,
                "new_actions": upgrade_actions or [],
                "approval_token": token,
                "status": "pending",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "applied_at": None,
                "backup_source": current_source,
            }

            changes: list[str] = []
            if current_version != _CURRENT_PATTERN_VERSION:
                changes.append(
                    f"Pattern version: {current_version} -> {_CURRENT_PATTERN_VERSION}"
                )
            if upgrade_actions:
                changes.append(f"New actions: {', '.join(upgrade_actions)}")

            return {
                "message": (
                    f"Evolution preview for '{agent_name}'. "
                    f"Pass approval_token to apply."
                ),
                "proposal_id": proposal_id,
                "approval_token": token,
                "agent_name": agent_name,
                "current_version": current_version,
                "target_version": _CURRENT_PATTERN_VERSION,
                "planned_changes": changes,
                "current_actions": current_actions,
                "new_actions": new_actions,
                "requires_approval": True,
            }

        proposal = None
        for p in _PROPOSALS.values():
            if p.get("approval_token") == approval_token and p.get("type") == "evolution":
                proposal = p
                break
        if not proposal:
            return {"message": "Invalid or expired approval token", "approved": False}

        evolved_source = current_source
        if 'pattern_version' in evolved_source:
            evolved_source = re.sub(
                r'(pattern_version.*?["\'])\d+\.\d+\.\d+(["\'])',
                f'\\g<1>{_CURRENT_PATTERN_VERSION}\\g<2>',
                evolved_source,
            )
        else:
            evolved_source = evolved_source.replace(
                '"status": "ready"',
                f'"status": "ready", "pattern_version": "{_CURRENT_PATTERN_VERSION}"',
            )

        if upgrade_actions:
            new_handlers = []
            for action in upgrade_actions:
                if f"handle_{action}" not in evolved_source:
                    new_handlers.append(
                        _HANDLER_TEMPLATE.format(action=action, agent_name=agent_name)
                    )
            if new_handlers:
                evolved_source = evolved_source.rstrip() + "\n\n" + "\n".join(new_handlers)

        target = _agent_file_path(agent_name)
        if target.exists():
            target.write_text(evolved_source, encoding="utf-8")

        try:
            mod = importlib.import_module(f"limbi.agents.{agent_name}")
            importlib.reload(mod)
        except Exception as exc:
            logger.warning("Hot-reload failed for %s: %s", agent_name, exc)

        proposal["status"] = "applied"
        proposal["applied_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        return {
            "message": f"Agent '{agent_name}' evolved to pattern v{_CURRENT_PATTERN_VERSION}",
            "approved": True,
            "agent_name": agent_name,
            "new_version": _CURRENT_PATTERN_VERSION,
            "actions_added": upgrade_actions or [],
        }

    def handle_list_mutations(self, status: str = "", **kw: Any) -> dict[str, Any]:
        items = list(_PROPOSALS.values())
        if status:
            items = [p for p in items if p["status"] == status]

        summary = []
        for p in items:
            summary.append({
                "id": p["id"],
                "agent_name": p["agent_name"],
                "status": p["status"],
                "type": p.get("type", "creation"),
                "created_at": p["created_at"],
                "applied_at": p.get("applied_at"),
            })

        return {
            "message": f"Found {len(summary)} mutation proposal(s)",
            "proposals": summary,
            "total": len(summary),
        }

    def handle_rollback(
        self,
        proposal_id: str = "",
        approval_token: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        if not proposal_id:
            raise ValueError("'proposal_id' is required")

        proposal = _PROPOSALS.get(proposal_id)
        if not proposal:
            return {"message": f"Proposal '{proposal_id}' not found", "rolled_back": False}

        if proposal["status"] != "applied":
            return {
                "message": f"Proposal is '{proposal['status']}' -- only 'applied' proposals can be rolled back",
                "rolled_back": False,
            }

        if not approval_token:
            token = hashlib.sha256(
                f"rollback:{proposal_id}:{time.time()}".encode()
            ).hexdigest()[:16]
            return {
                "message": "Rollback requires approval",
                "approval_token": token,
                "requires_approval": True,
                "proposal_id": proposal_id,
            }

        agent_name = proposal["agent_name"]

        if proposal.get("type") == "evolution" and proposal.get("backup_source"):
            target = _agent_file_path(agent_name)
            if target.exists():
                target.write_text(proposal["backup_source"], encoding="utf-8")
        else:
            target = _agent_file_path(agent_name)
            if target.exists():
                target.unlink()

            if agent_name in _AGENT_REGISTRY:
                del _AGENT_REGISTRY[agent_name]

        proposal["status"] = "rolled_back"

        return {
            "message": f"Mutation '{proposal_id}' rolled back for '{agent_name}'",
            "rolled_back": True,
            "agent_name": agent_name,
        }
