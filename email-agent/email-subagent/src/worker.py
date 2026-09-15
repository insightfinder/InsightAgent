"""
Temporal Worker for SubagentDraftWorkflow.
"""
import asyncio

from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions
import structlog

from .config import get_settings
from .logging_setup import configure_logging
from .tracing import setup_tracing
from .workflows import SubagentDraftWorkflow
from .activities.subagent import draft_email_activity

configure_logging()
logger = structlog.get_logger()

# structlog/rich: same sandbox-incompatibility as every other worker.py in
# this repo. httpx/anthropic: the model call in draft_email_activity is
# reached via `imports_passed_through()` in the workflow file, so its
# transitive imports need to be in this worker-level list too.
_PASSTHROUGH_MODULES = [
    "httpx", "httpx.*",
    "anthropic", "anthropic.*",
    "structlog", "structlog.*",
    "rich", "rich.*",
    "logging", "logging.*",
]


async def run_worker():
    settings = get_settings()
    setup_tracing(settings, f"{settings.service_name}-worker")

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
        workflows=[SubagentDraftWorkflow],
        activities=[draft_email_activity],
        interceptors=interceptors,
        workflow_runner=SandboxedWorkflowRunner(restrictions=sandbox_restrictions),
    )

    logger.info("Starting Temporal worker", task_queue=settings.temporal_task_queue)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
