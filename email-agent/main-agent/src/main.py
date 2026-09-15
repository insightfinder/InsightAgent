import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import structlog

from .config import get_settings
from .logging_setup import configure_logging
from .tracing import setup_tracing, instrument_fastapi
from .workflows import MainAgentWorkflow

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
    logger.info("Starting Main Agent Service", port=settings.http_port)
    await get_temporal_client()
    logger.info("Connected to Temporal", address=settings.temporal_address)
    yield
    logger.info("Main Agent Service shutdown")


app = FastAPI(
    title="Main Agent Service",
    description="Main agent (II-24784): receives user input, calls the email-subagent, sends the confirmed email",
    version="0.1.0",
    lifespan=lifespan,
)

# At import time, NOT inside lifespan: Starlette builds its middleware stack
# on the app's first __call__, and the lifespan scope IS that first call --
# so middleware added from inside lifespan lands in user_middleware but never
# in the stack that serves requests. It logs success and produces no server
# span at all.
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


class StartTaskRequest(BaseModel):
    user_message: str
    to_email: str
    subject: str


class ConfirmRequest(BaseModel):
    confirmed: bool


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/tasks")
async def start_task(request: StartTaskRequest):
    client = await get_temporal_client()
    settings = get_settings()
    task_id = str(uuid.uuid4())

    await client.start_workflow(
        MainAgentWorkflow.run,
        args=[request.user_message, request.to_email, request.subject],
        id=task_id,
        task_queue=settings.temporal_task_queue,
    )
    logger.info("Task started", task_id=task_id)
    return {"task_id": task_id, "status": "started"}


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    client = await get_temporal_client()
    handle = client.get_workflow_handle(task_id)
    try:
        return await handle.query(MainAgentWorkflow.get_status)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Task not found: {e}")


@app.post("/tasks/{task_id}/confirm")
async def confirm_task(task_id: str, request: ConfirmRequest):
    client = await get_temporal_client()
    handle = client.get_workflow_handle(task_id)
    try:
        await handle.signal(MainAgentWorkflow.confirm_send, request.confirmed)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Task not found: {e}")
    return {"task_id": task_id, "confirmed": request.confirmed}


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.http_port)
