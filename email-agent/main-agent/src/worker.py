"""
Temporal Worker for MainAgentWorkflow.
"""
import asyncio

from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions
import structlog

from .config import get_settings
from .logging_setup import configure_logging
from .tracing import setup_tracing, instrument_httpx
from .workflows import MainAgentWorkflow
from .activities.main_agent import call_subagent_activity, send_email_activity

configure_logging()
logger = structlog.get_logger()

_PASSTHROUGH_MODULES = [
    "httpx", "httpx.*",
    "structlog", "structlog.*",
    "rich", "rich.*",
    "logging", "logging.*",
]


async def run_worker():
    settings = get_settings()
    setup_tracing(settings, f"{settings.service_name}-worker")
    if settings.enable_tracing:
        # call_subagent_activity's outgoing HTTP call happens in THIS process,
        # not the API one -- without instrumenting httpx here the request
        # carries no traceparent and the subagent opens a second, unrelated
        # trace, so the two pods never appear as one multi-component trace.
        instrument_httpx(f"{settings.service_name}-worker")

    logger.info(
        "Connecting to Temporal",
        address=settings.temporal_address,
        namespace=settings.temporal_namespace,
    )

    from temporalio.contrib.opentelemetry import TracingInterceptor

    interceptors = [TracingInterceptor()] if settings.enable_tracing else []
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        interceptors=interceptors,
    )

    sandbox_restrictions = SandboxRestrictions.default.with_passthrough_modules(*_PASSTHROUGH_MODULES)

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[MainAgentWorkflow],
        activities=[call_subagent_activity, send_email_activity],
        interceptors=interceptors,
        workflow_runner=SandboxedWorkflowRunner(restrictions=sandbox_restrictions),
    )

    logger.info("Starting Temporal worker", task_queue=settings.temporal_task_queue)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
