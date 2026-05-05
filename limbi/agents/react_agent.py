

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import BaseAgent, get_agent, list_agents

logger = logging.getLogger("limbi.agents.react")

@dataclass
class ReActStep:

    step_num: int
    thought: str = ""
    action: str = ""
    action_input: dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "step": self.step_num,
            "thought": self.thought,
            "action": self.action,
            "action_input": self.action_input,
            "observation": self.observation,
        }

@dataclass
class ReActTrace:

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    query: str = ""
    steps: list[ReActStep] = field(default_factory=list)
    final_answer: str = ""
    status: str = "running"
    total_time_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "query": self.query,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "step_count": len(self.steps),
            "final_answer": self.final_answer,
            "total_time_ms": round(self.total_time_ms, 1),
        }

_traces: dict[str, ReActTrace] = {}

class ReActAgent(BaseAgent):

    agent_name = "react_agent"

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "react_reasoning",
            "status": "ready",
            "available_tools": list(list_agents().keys()),
            "stored_traces": len(_traces),
        }

    def handle_reason(
        self,
        query: str = "",
        max_steps: int = 5,
        plan: list[dict[str, Any]] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        if not query:
            raise ValueError("A 'query' is required")

        start_time = time.time()
        trace = ReActTrace(query=query)

        if plan:

            for i, step_plan in enumerate(plan[:max_steps]):
                step = ReActStep(step_num=i + 1)
                step.thought = step_plan.get("thought", f"Executing step {i + 1}")

                agent_name = step_plan.get("agent", "")
                action_name = step_plan.get("action", "")
                params = step_plan.get("params", {})

                if agent_name and action_name:
                    step.action = f"{agent_name}.{action_name}"
                    step.action_input = params

                    try:
                        agent = get_agent(agent_name)
                        result = agent.execute(action_name, params)
                        if result.success:
                            step.observation = f" Success: {_summarize_dict(result.data)}"
                        else:
                            step.observation = f" Failed: {result.error}"
                    except Exception as exc:
                        step.observation = f" Error: {exc}"
                else:
                    step.action = "think"
                    step.observation = "Reasoning step - no external action needed"

                trace.steps.append(step)
        else:

            trace.steps = self._heuristic_reason(query, max_steps)

        observations = [s.observation for s in trace.steps if s.observation]
        trace.final_answer = self._synthesize_answer(query, trace.steps)
        trace.status = "completed"
        trace.total_time_ms = (time.time() - start_time) * 1000

        _traces[trace.id] = trace

        return {
            "message": f"ReAct trace completed in {len(trace.steps)} steps",
            **trace.to_dict(),
        }

    def _heuristic_reason(self, query: str, max_steps: int) -> list[ReActStep]:

        steps: list[ReActStep] = []
        query_lower = query.lower()

        step1 = ReActStep(step_num=1, thought="First, I need to understand what this query is about and which agents can help.")
        try:
            router = get_agent("router_agent")
            result = router.execute("route", {"query": query})
            if result.success:
                primary = result.data.get("primary_route", {})
                step1.action = "router_agent.route"
                step1.action_input = {"query": query}
                step1.observation = f"Best match: {primary.get('agent', '?')}.{primary.get('suggested_action', '?')} (confidence: {primary.get('confidence', '?')})"
            else:
                step1.observation = "Router couldn't find a match - will use general reasoning"
        except Exception:
            step1.observation = "Router unavailable - proceeding with heuristic analysis"
        steps.append(step1)

        if step1.observation.startswith("Best match:"):
            try:
                route = result.data.get("primary_route", {})
                agent_name = route["agent"]
                action_name = route["suggested_action"]

                step2 = ReActStep(
                    step_num=2,
                    thought=f"The router suggests {agent_name}.{action_name}. Let me execute it.",
                    action=f"{agent_name}.{action_name}",
                    action_input={},
                )

                agent = get_agent(agent_name)
                exec_result = agent.execute(action_name, {})
                if exec_result.success:
                    step2.observation = f" {_summarize_dict(exec_result.data)}"
                else:
                    step2.observation = f" {exec_result.error}"
                steps.append(step2)
            except Exception as exc:
                steps.append(ReActStep(
                    step_num=2,
                    thought="Attempting to execute the suggested action",
                    observation=f" Error: {exc}",
                ))

        if len(steps) >= 2:
            step3 = ReActStep(
                step_num=3,
                thought="Let me synthesize what I've learned from these observations.",
                action="think",
                observation="Reasoning complete - ready to provide an answer.",
            )
            steps.append(step3)

        return steps[:max_steps]

    def _synthesize_answer(self, query: str, steps: list[ReActStep]) -> str:

        parts = [f"**Query:** {query}\n"]
        parts.append("**Reasoning Trace:**\n")
        for step in steps:
            parts.append(f"  {step.step_num}.  {step.thought}")
            if step.action and step.action != "think":
                parts.append(f"      Action: `{step.action}`")
            parts.append(f"      {step.observation}")
            parts.append("")

        return "\n".join(parts)

    def handle_get_trace(self, trace_id: str = "", **kw: Any) -> dict[str, Any]:

        trace = _traces.get(trace_id)
        if not trace:
            return {"message": f"Trace '{trace_id}' not found", "available": list(_traces.keys())}
        return trace.to_dict()

    def handle_list_traces(self, limit: int = 10, **kw: Any) -> dict[str, Any]:

        traces = sorted(_traces.values(), key=lambda t: t.total_time_ms, reverse=True)[:limit]
        return {
            "traces": [
                {"id": t.id, "query": t.query[:60], "steps": len(t.steps), "status": t.status}
                for t in traces
            ],
            "total": len(_traces),
        }

class TaskLoopAgent(BaseAgent):

    agent_name = "taskloop_agent"

    def __init__(self) -> None:
        self._active_loops: dict[str, dict[str, Any]] = {}

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "type": "autonomous_task_loop",
            "status": "ready",
            "active_loops": len(self._active_loops),
        }

    def handle_start_loop(
        self,
        goal: str = "",
        initial_tasks: list[str] | None = None,
        max_iterations: int = 10,
        **kw: Any,
    ) -> dict[str, Any]:

        if not goal:
            raise ValueError("A 'goal' is required")

        loop_id = str(uuid.uuid4())[:8]
        tasks = initial_tasks or self._decompose_goal(goal)

        loop = {
            "id": loop_id,
            "goal": goal,
            "tasks": [{"title": t, "status": "pending", "result": None} for t in tasks],
            "completed_tasks": [],
            "iterations": 0,
            "max_iterations": max_iterations,
            "status": "running",
            "insights": [],
        }

        if loop["tasks"]:
            first = loop["tasks"][0]
            first["status"] = "in_progress"
            first["result"] = self._execute_task(first["title"], goal)
            first["status"] = "completed"
            loop["completed_tasks"].append(first)
            loop["tasks"] = loop["tasks"][1:]
            loop["iterations"] = 1

            new_tasks = self._gen_followup_tasks(goal, first, loop["tasks"])
            for nt in new_tasks:
                loop["tasks"].append({"title": nt, "status": "pending", "result": None})

        if not loop["tasks"]:
            loop["status"] = "completed"

        self._active_loops[loop_id] = loop

        return {
            "message": f"Task loop started for: '{goal}'",
            "loop_id": loop_id,
            "goal": goal,
            "tasks_remaining": len(loop["tasks"]),
            "tasks_completed": len(loop["completed_tasks"]),
            "completed_task": loop["completed_tasks"][-1] if loop["completed_tasks"] else None,
            "next_tasks": [t["title"] for t in loop["tasks"][:3]],
            "status": loop["status"],
        }

    def handle_iterate(self, loop_id: str = "", **kw: Any) -> dict[str, Any]:

        loop = self._active_loops.get(loop_id)
        if not loop:
            raise ValueError(f"Loop '{loop_id}' not found")
        if loop["status"] != "running":
            return {"message": f"Loop is {loop['status']}", **loop}
        if loop["iterations"] >= loop["max_iterations"]:
            loop["status"] = "max_iterations_reached"
            return {"message": "Maximum iterations reached", **loop}
        if not loop["tasks"]:
            loop["status"] = "completed"
            return {"message": "All tasks completed!", **loop}

        task = loop["tasks"][0]
        task["status"] = "in_progress"
        task["result"] = self._execute_task(task["title"], loop["goal"])
        task["status"] = "completed"
        loop["completed_tasks"].append(task)
        loop["tasks"] = loop["tasks"][1:]
        loop["iterations"] += 1

        new_tasks = self._gen_followup_tasks(loop["goal"], task, loop["tasks"])
        for nt in new_tasks:
            loop["tasks"].append({"title": nt, "status": "pending", "result": None})

        if not loop["tasks"]:
            loop["status"] = "completed"

        return {
            "message": f"Iteration {loop['iterations']}: completed '{task['title']}'",
            "loop_id": loop_id,
            "completed_task": task,
            "tasks_remaining": len(loop["tasks"]),
            "next_tasks": [t["title"] for t in loop["tasks"][:3]],
            "status": loop["status"],
        }

    def handle_get_loop(self, loop_id: str = "", **kw: Any) -> dict[str, Any]:

        loop = self._active_loops.get(loop_id)
        if not loop:
            raise ValueError(f"Loop '{loop_id}' not found")
        return {
            **loop,
            "pending_titles": [t["title"] for t in loop["tasks"]],
            "completed_titles": [t["title"] for t in loop["completed_tasks"]],
        }

    def handle_list_loops(self, **kw: Any) -> dict[str, Any]:

        return {
            "loops": [
                {
                    "id": l["id"],
                    "goal": l["goal"][:60],
                    "status": l["status"],
                    "iterations": l["iterations"],
                    "tasks_remaining": len(l["tasks"]),
                }
                for l in self._active_loops.values()
            ],
        }

    def _decompose_goal(self, goal: str) -> list[str]:

        goal_lower = goal.lower()
        tasks = []

        if any(w in goal_lower for w in ["deploy", "release", "ship"]):
            tasks = [
                f"Check current deployment status",
                f"Run test pipeline for the target branch",
                f"Create deployment PR if needed",
                f"Deploy to staging environment",
                f"Verify staging health",
                f"Create tracking ticket in Jira",
            ]
        elif any(w in goal_lower for w in ["fix", "bug", "debug"]):
            tasks = [
                f"Investigate the reported issue",
                f"Check recent deployments for regressions",
                f"Create a fix branch",
                f"Implement and test the fix",
                f"Create a PR for review",
                f"Update the relevant Jira ticket",
            ]
        elif any(w in goal_lower for w in ["setup", "initialize", "create project"]):
            tasks = [
                f"Create repository structure",
                f"Generate boilerplate code",
                f"Set up CI/CD pipeline",
                f"Create initial Jira board",
                f"Document the setup process",
            ]
        else:
            tasks = [
                f"Analyze requirements for: {goal}",
                f"Identify necessary resources",
                f"Create implementation plan",
                f"Execute primary action",
                f"Verify results",
            ]

        return tasks

    def _execute_task(self, title: str, goal: str) -> str:

        title_lower = title.lower()

        try:
            if any(w in title_lower for w in ["deploy", "pipeline", "status", "health"]):
                agent = get_agent("devops_agent")
                if "status" in title_lower or "health" in title_lower:
                    r = agent.execute("check_status", {})
                elif "pipeline" in title_lower:
                    r = agent.execute("run_pipeline", {})
                else:
                    r = agent.execute("deploy_branch", {})
                return f"{'' if r.success else ''} {_summarize_dict(r.data)}"

            elif any(w in title_lower for w in ["branch", "pr", "merge", "repo"]):
                agent = get_agent("git_agent")
                if "pr" in title_lower:
                    r = agent.execute("create_pr", {"title": title})
                elif "branch" in title_lower:
                    r = agent.execute("create_branch", {"branch": "auto-" + str(uuid.uuid4())[:6]})
                else:
                    r = agent.execute("list_repos", {})
                return f"{'' if r.success else ''} {_summarize_dict(r.data)}"

            elif any(w in title_lower for w in ["ticket", "jira", "track"]):
                agent = get_agent("jira_agent")
                r = agent.execute("create_ticket", {"title": title, "priority": "Medium"})
                return f"{'' if r.success else ''} {_summarize_dict(r.data)}"

            else:
                return f" Task noted for manual attention: {title}"

        except Exception as exc:
            return f" Error: {exc}"

    def _gen_followup_tasks(
        self, goal: str, completed_task: dict[str, Any], remaining: list[dict[str, Any]]
    ) -> list[str]:

        result = completed_task.get("result", "")
        if "" in str(result):
            return [f"Retry or fix: {completed_task['title']}"]
        return []

def _summarize_dict(d: dict[str, Any], max_len: int = 150) -> str:

    msg = d.get("message", "")
    if msg:
        return msg[:max_len]
    return str(d)[:max_len]
