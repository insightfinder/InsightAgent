import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import structlog

from .config import get_settings
from .logging_setup import configure_logging
from .tracing import setup_tracing, instrument_fastapi
from .workflows import SubagentDraftWorkflow

configure_logging()
logger = structlog.get_logger()

_temporal_client = None


async def get_temporal_client():
    global _temporal_client
    if _temporal_client is None:
        from temporalio.client import Client
        from temporalio.contrib.opentelemetry import TracingInterceptor

        settings = get_settings()
        interceptors = [TracingInterceptor()] if settings.enable_tracing else []
        _temporal_client = await Client.connect(
            settings.temporal_address,
            namespace=settings.temporal_namespace,
            interceptors=interceptors,
        )
    return _temporal_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting Email Subagent Service", port=settings.http_port)
    await get_temporal_client()
    logger.info("Connected to Temporal", address=settings.temporal_address)
    yield
    logger.info("Email Subagent Service shutdown")


app = FastAPI(
    title="Email Subagent Service",
    description="Email-drafting subagent, called over HTTP by main-agent (II-24784)",
    version="0.1.0",
    lifespan=lifespan,
)

# At import time, NOT inside lifespan: Starlette builds its middleware stack
# on the app's first __call__, and the lifespan scope IS that first call --
# so middleware added from inside lifespan lands in user_middleware but never
# in the stack that serves requests. It logs success and produces no server
# span, which silently drops the incoming traceparent and makes this service
# start its own trace instead of continuing the caller's.
_settings = get_settings()
setup_tracing(_settings, _settings.service_name)
if _settings.enable_tracing:
    instrument_fastapi(app, _settings.service_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DraftRequest(BaseModel):
    to_email: str
    subject: str
    brief: str


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/draft")
async def draft(request: DraftRequest):
    """
    Synchronous-style endpoint: starts (and waits for) a
    SubagentDraftWorkflow. Called by main-agent's call_subagent_activity.

    Runs within the caller's own trace context (FastAPIInstrumentor
    extracts the incoming traceparent header automatically), so the
    workflow/activity spans this starts nest under main-agent's activity
    span that made the HTTP call -- no manual trace-context plumbing needed.
    """
    client = await get_temporal_client()
    settings = get_settings()
    workflow_id = str(uuid.uuid4())

    handle = await client.start_workflow(
        SubagentDraftWorkflow.run,
        args=[request.to_email, request.subject, request.brief],
        id=workflow_id,
        task_queue=settings.temporal_task_queue,
    )
    try:
        result = await handle.result()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Drafting failed: {e}")
    return result


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.http_port)
