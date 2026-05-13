

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import huggingface_hub
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

def _patch_huggingface_hub_compat() -> None:
    if hasattr(huggingface_hub, "HfFolder"):
        return

    token_path = Path(
        os.getenv(
            "HF_TOKEN_PATH",
            str(Path.home() / ".cache" / "huggingface" / "token"),
        )
    )

    class CompatHfFolder:
        path_token = str(token_path)

        @classmethod
        def save_token(cls, token: str) -> None:
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(token, encoding="utf-8")

        @classmethod
        def get_token(cls) -> Optional[str]:
            token = huggingface_hub.get_token()
            if token:
                return token
            if token_path.is_file():
                return token_path.read_text(encoding="utf-8").strip() or None
            return None

        @classmethod
        def delete_token(cls) -> None:
            if token_path.exists():
                token_path.unlink()

    huggingface_hub.HfFolder = CompatHfFolder

_patch_huggingface_hub_compat()

import gradio as gr

load_dotenv()

import agents.devops_agent
import agents.git_agent
import agents.jira_agent
import agents.aws_agent

import agents.reflex_agent
import agents.planner_agent

import agents.critic_agent
import agents.code_agent
import agents.router_agent
import agents.memory_agent
import agents.react_agent
import agents.learning_agent

import agents.research_agent
import agents.data_agent
import agents.comms_agent
import agents.docs_agent
import agents.qa_agent
import agents.security_agent
import agents.database_agent
import agents.scheduler_agent
import agents.file_agent
import agents.swarm_agent
import agents.browser_agent
import agents.web_scraping_agent
import agents.os_agent
import agents.tool_builder_agent
import agents.integration_agent
import agents.auth_agent
import agents.observability_agent
import agents.workflow_agent
import agents.approval_agent
import agents.policy_agent
import agents.multimodal_agent
import agents.design_agent
import agents.customer_support_agent
import agents.sales_agent
import agents.finance_agent
import agents.legal_agent
import agents.knowledge_agent
import agents.simulation_agent
import agents.evaluation_agent
import agents.healthcare_agent
import agents.education_agent
import agents.hr_agent
import agents.recruiting_agent
import agents.procurement_agent
import agents.real_estate_agent
import agents.ecommerce_agent
import agents.marketing_agent
import agents.social_media_agent
import agents.blockchain_agent
import agents.iot_agent
import agents.travel_agent
import agents.manufacturing_agent
import agents.customer_success_agent
import agents.insurance_agent
import agents.logistics_agent
import agents.hospitality_agent
import agents.agriculture_agent
import agents.media_agent
import agents.government_agent

import agents.analytics_agent
import agents.compliance_agent
import agents.incident_agent
import agents.testing_agent
import agents.gcp_agent
import agents.azure_agent
import agents.nlp_agent
import agents.project_management_agent
import agents.kubernetes_agent
import agents.notification_agent
import agents.performance_agent
import agents.migration_agent
import agents.cost_agent
import agents.cicd_agent
import agents.onboarding_agent
import agents.reporting_agent
import agents.sre_agent
import agents.documentation_agent
import agents.feature_flag_agent
import agents.api_gateway_agent
import agents.energy_agent
import agents.sustainability_agent
import agents.feedback_agent
import agents.payments_agent
import agents.context_memory_agent
import agents.mutation_agent

from agents import get_agent, list_agents
from orchestrator import Orchestrator
from payload_parser import parse_llm_output
from audit_log import init_db, get_recent_executions, get_execution_stats, log_webhook
from middleware import ApiKeyAuthMiddleware, RateLimitMiddleware, get_cors_origins, get_rate_limit_status
from llm_provider import get_llm_provider, list_providers

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("limbi")

@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info(" Limbi v2 starting up...")

    init_db()
    logger.info(" Audit log ready")

    app.state.orchestrator = Orchestrator()
    provider = get_llm_provider()
    logger.info(" Orchestrator ready (provider=%s, model=%s)", provider.provider_name(), provider.config.model)

    agents_info = list_agents()
    for name, actions in agents_info.items():
        logger.info("   %s -> %s", name, ", ".join(actions))

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}/api/tags",
                timeout=3.0,
            )
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                logger.info(" Ollama connected - models: %s", ", ".join(models) or "none")
            else:
                logger.warning(" Ollama returned %d", resp.status_code)
    except Exception as exc:
        logger.warning(" Ollama not reachable (%s) - start with: ollama serve", exc)

    yield

    logger.info(" Limbi shutting down")

app = FastAPI(
    title="Limbi - Omni-Agent Orchestrator",
    version="2.0.0",
    description=(
        "Intelligent AI orchestrator with a swarm of specialised agents "
        "for DevOps, Git, Jira, and AWS operations. "
        "Features streaming, parallel execution, retry logic, and audit logging."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ApiKeyAuthMiddleware)
app.add_middleware(RateLimitMiddleware)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = datetime.now(timezone.utc)
    response = await call_next(request)
    duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

    if request.url.path != "/favicon.ico" and not request.url.path.startswith("/extension"):
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
    return response

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000, description="User message")
    stream: bool = Field(default=False, description="Enable SSE streaming")

class ChatResponse(BaseModel):
    conversation_text: str
    delegations_executed: list[dict[str, Any]] = []
    errors: list[str] = []
    timestamp: str = ""

class DelegationRequest(BaseModel):
    action: str = Field(..., description="Action to execute")
    params: dict[str, Any] = Field(default_factory=dict, description="Action parameters")

class IngestRequest(BaseModel):
    directory: str = Field(..., description="Absolute path to the directory to index")
    chunk_size: int = Field(default=1000, ge=100, le=5000)
    chunk_overlap: int = Field(default=200, ge=0, le=1000)

class WebhookPayload(BaseModel):
    agent: str = Field(..., description="Agent that completed the action")
    action: str = Field(..., description="Action that completed")
    correlation_id: Optional[str] = Field(default=None, description="Correlation ID from original request")
    status: str = Field(default="success", description="Outcome status")
    data: dict[str, Any] = Field(default_factory=dict)

def _get_orchestrator() -> Orchestrator:
    orchestrator = getattr(app.state, "orchestrator", None)
    if orchestrator is None:
        orchestrator = Orchestrator()
        app.state.orchestrator = orchestrator
    return orchestrator

def _gradio_status_text() -> str:
    provider = get_llm_provider()
    provider_info = provider.info()
    return (
        f"**Provider:** `{provider.provider_name()}`  \n"
        f"**Model:** `{provider_info.get('model', 'unknown')}`  \n"
        f"**Agents Available:** `{len(list_agents())}`  \n"
        f"**Build Path:** `Ollama -> Orchestrator -> Agents`"
    )

async def _gradio_send_message(
    message: str,
    history: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], str]:
    text = (message or "").strip()
    if not text:
        return history, ""

    orchestrator = _get_orchestrator()
    result = await orchestrator.chat(text)
    reply = result.get("conversation_text", "").strip() or "No response returned."

    if result.get("errors"):
        error_lines = "\n".join(f"- {err}" for err in result["errors"])
        reply = f"{reply}\n\n**Errors**\n{error_lines}"

    updated_history = history + [(text, reply)]
    return updated_history, ""

def _gradio_clear_chat() -> tuple[list[tuple[str, str]], str]:
    orchestrator = _get_orchestrator()
    orchestrator.clear_history()
    return [], ""

def _build_gradio_ui() -> gr.Blocks:
    theme = gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="sky",
        neutral_hue="slate",
    ).set(
        body_background_fill="#f8fafc",
        body_background_fill_dark="#f8fafc",
        block_background_fill="#ffffff",
        block_background_fill_dark="#ffffff",
        input_background_fill="#ffffff",
        input_background_fill_dark="#ffffff",
    )

    with gr.Blocks(
        title="Limbi Builder",
        theme=theme,
        fill_height=True,
        css="""
        body, .gradio-container {
            background: #f8fafc !important;
            color: #0f172a !important;
        }
        .gradio-container {
            max-width: 1100px !important;
            margin: 0 auto !important;
        }
        .app-shell {
            border: 1px solid #dbeafe;
            background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(15, 23, 42, 0.08);
            padding: 12px;
        }
        """,
    ) as demo:
        with gr.Column(elem_classes=["app-shell"]):
            gr.Markdown(
                """
                # Limbi Builder
                Ask Limbi to build code, APIs, docs, workflows, or automation tasks.
                Your prompt is sent to Ollama through the shared orchestrator, and Limbi can delegate work to the connected agents when needed.
                """
            )
            with gr.Row():
                status = gr.Markdown(_gradio_status_text())
                refresh = gr.Button("Refresh Status", variant="secondary")
            chatbot = gr.Chatbot(
                value=[],
                height=520,
                bubble_full_width=False,
                show_copy_button=True,
                label="Build Chat",
            )
            with gr.Row():
                message = gr.Textbox(
                    label="What do you want to build?",
                    placeholder=(
                        "Example: Build a FastAPI service for invoice uploads, "
                        "add a README, and create tests with the connected agents."
                    ),
                    lines=2,
                    max_lines=8,
                    scale=8,
                )
            with gr.Row():
                send = gr.Button("Send", variant="primary")
                clear = gr.Button("Clear Chat", variant="secondary")
            gr.Examples(
                examples=[
                    "Build a FastAPI CRUD service for tasks with Pydantic models and a README.",
                    "Create a Python CLI tool that scans a folder and summarizes file types.",
                    "Generate a deployment checklist and rollout plan for a staging release.",
                    "Design a webhook payload format and sample handler for GitHub events.",
                ],
                inputs=message,
            )

        send.click(_gradio_send_message, inputs=[message, chatbot], outputs=[chatbot, message])
        message.submit(_gradio_send_message, inputs=[message, chatbot], outputs=[chatbot, message])
        clear.click(_gradio_clear_chat, outputs=[chatbot, message])
        refresh.click(_gradio_status_text, outputs=status)
        demo.load(_gradio_status_text, outputs=status)

    demo.queue(default_concurrency_limit=8)
    return demo

@app.get("/", tags=["root"])
async def root():
    return {
        "service": "Limbi - Omni-Agent Orchestrator",
        "version": "2.0.0",
        "status": "operational",
        "features": [
            "SSE streaming", "parallel agent execution",
            "retry with backoff", "rate limiting",
            "conversation summarization", "audit logging",
            "webhook callbacks", "smart RAG chunking",
        ],
        "endpoints": {
            "chat": "/api/chat",
            "chat_stream": "/api/chat (with stream: true)",
            "agents": "/api/agents",
            "audit": "/api/audit",
            "webhooks": "/api/webhooks",
            "health": "/health",
            "docs": "/docs",
            "ui": "/ui",
        },
    }

@app.get("/health", tags=["monitoring"])
async def health_check():
    agents_info = list_agents()

    provider = get_llm_provider()
    provider_info = provider.info()
    llm_status = "configured"

    if provider.provider_name() == "ollama":
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{provider.config.base_url}/api/tags",
                    timeout=2.0,
                )
                if resp.status_code == 200:
                    llm_status = "connected"
                    ollama_models = [m["name"] for m in resp.json().get("models", [])]
                    provider_info["available_models"] = ollama_models
                else:
                    llm_status = f"error ({resp.status_code})"
        except Exception:
            llm_status = "unreachable"

    rate_info = get_rate_limit_status()

    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "llm_provider": {
            **provider_info,
            "status": llm_status,
        },
        "supported_providers": list_providers(),
        "agents_registered": len(agents_info),
        "agents": list(agents_info.keys()),
        "rate_limiting": rate_info,
    }

@app.post("/api/chat", tags=["orchestrator"])
async def chat(req: ChatRequest, request: Request):

    orchestrator: Orchestrator = request.app.state.orchestrator

    if req.stream:
        return StreamingResponse(
            _stream_chat(orchestrator, req.message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    result = await orchestrator.chat(req.message)
    result["timestamp"] = datetime.now(timezone.utc).isoformat()
    return result

async def _stream_chat(orchestrator: Orchestrator, message: str):

    async for event in orchestrator.chat_stream(message):
        yield f"data: {json.dumps(event)}\n\n"
    yield "data: [DONE]\n\n"

@app.post("/api/chat/clear", tags=["orchestrator"])
async def clear_chat(request: Request):

    orchestrator: Orchestrator = request.app.state.orchestrator
    orchestrator.clear_history()
    return {"message": "Conversation history cleared"}

@app.get("/api/agents", tags=["agents"])
async def get_agents():

    agents_info = list_agents()
    agent_health = {}
    for name in agents_info:
        try:
            agent = get_agent(name)
            agent_health[name] = {
                "actions": agents_info[name],
                "health": agent.health_check(),
            }
        except Exception as exc:
            logger.warning("Health check failed for %s: %s", name, exc)
            agent_health[name] = {
                "actions": agents_info[name],
                "error": "Health check failed",
            }
    return {"agents": agent_health}

@app.post("/api/agents/{agent_name}/{action}", tags=["agents"])
async def execute_agent_action(
    agent_name: str,
    action: str,
    req: Optional[DelegationRequest] = None,
):

    try:
        agent = get_agent(agent_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent not found")

    params = req.params if req else {}
    result = agent.execute(action, params)

    if not result.success:
        detail = result.error if result.error and result.error.startswith("Unknown action") else "Agent action failed"
        raise HTTPException(status_code=400, detail=detail)

    return result.to_dict()

@app.post("/api/devops/deploy", tags=["agents", "devops"])
async def devops_deploy(branch: str = "main", env: str = "staging"):
    try:
        agent = get_agent("devops_agent")
        result = agent.execute("deploy_branch", {"branch": branch, "env": env})
        if not result.success:
            raise HTTPException(status_code=400, detail="Agent action failed")
        return result.to_dict()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("DevOps deploy failed: %s", exc)
        raise HTTPException(status_code=500, detail="Agent action failed")

@app.post("/api/git/merge", tags=["agents", "git"])
async def git_merge(repo: str = "", head: str = "", base: str = "main"):
    try:
        agent = get_agent("git_agent")
        result = agent.execute("merge", {"repo": repo, "head": head, "base": base})
        if not result.success:
            raise HTTPException(status_code=400, detail="Agent action failed")
        return result.to_dict()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Git merge failed: %s", exc)
        raise HTTPException(status_code=500, detail="Agent action failed")

@app.post("/api/jira/create", tags=["agents", "jira"])
async def jira_create_ticket(title: str = "", priority: str = "Medium", description: str = ""):
    try:
        agent = get_agent("jira_agent")
        result = agent.execute("create_ticket", {
            "title": title, "priority": priority, "description": description,
        })
        if not result.success:
            raise HTTPException(status_code=400, detail="Agent action failed")
        return result.to_dict()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Jira ticket creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Agent action failed")

@app.get("/api/audit/executions", tags=["audit"])
async def audit_recent(limit: int = 20):

    return {"executions": get_recent_executions(limit=min(limit, 100))}

@app.get("/api/audit/stats", tags=["audit"])
async def audit_stats():

    return get_execution_stats()

@app.post("/api/webhooks/agent-callback", tags=["webhooks"])
async def webhook_agent_callback(payload: WebhookPayload):

    row_id = log_webhook(
        agent=payload.agent,
        action=payload.action,
        correlation_id=payload.correlation_id,
        payload=payload.data,
        status=payload.status,
    )
    logger.info(
        "Webhook received: %s.%s (correlation=%s, status=%s)",
        payload.agent, payload.action, payload.correlation_id, payload.status,
    )
    return {
        "received": True,
        "webhook_id": row_id,
        "message": f"Callback for {payload.agent}.{payload.action} logged",
    }

@app.post("/api/rag/ingest", tags=["rag"])
async def ingest_codebase(req: IngestRequest, request: Request):
    orchestrator: Orchestrator = request.app.state.orchestrator
    try:
        result = orchestrator.ingest_codebase(req.directory)
        return {"status": "success", **result}
    except Exception as exc:
        logger.exception("RAG ingest failed: %s", exc)
        raise HTTPException(status_code=400, detail="RAG ingest failed")

@app.get("/api/rag/stats", tags=["rag"])
async def rag_stats(request: Request):
    orchestrator: Orchestrator = request.app.state.orchestrator
    return orchestrator.vector_store_stats()

@app.get("/api/rag/query", tags=["rag"])
async def rag_query(q: str, n: int = 5, request: Request = None):

    orchestrator: Orchestrator = request.app.state.orchestrator
    try:
        results = orchestrator._vector_store.query(q, n_results=n)
        return {"query": q, "results": results, "count": len(results)}
    except Exception as exc:
        logger.exception("RAG query failed: %s", exc)
        raise HTTPException(status_code=400, detail="RAG query failed")

@app.get("/api/system/rate-limits", tags=["system"])
async def system_rate_limits():

    return get_rate_limit_status()

@app.post("/api/debug/parse", tags=["debug"])
async def debug_parse(raw: str):

    result = parse_llm_output(raw)
    return result.to_dict()

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

_static_dir = os.path.join(os.path.dirname(__file__), "static", "extension")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

if os.path.isdir(_static_dir):
    app.mount("/extension", StaticFiles(directory=_static_dir), name="extension")

app = gr.mount_gradio_app(app, _build_gradio_ui(), path="/ui")
