#!/usr/bin/env python3
"""
MULTI-AGENT AI SYSTEM (Anthropic Claude)
=========================================

Multi-agent architecture with specialized agents:
- CoordinatorAgent: Orchestrates the workflow
- AnalyzerAgent: Analyzes tasks using AI
- DrafterAgent: Drafts emails
- ExecutorAgent: Executes actions

Each agent is a separate workflow with its own responsibilities.
"""

import argparse
import asyncio
import os
import sys
import time
import uuid
from datetime import timedelta
from dataclasses import dataclass
from typing import Optional
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions
from temporalio import workflow, activity
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

# OpenTelemetry imports
from opentelemetry import trace, context as otel_context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
from temporalio.contrib.opentelemetry import TracingInterceptor

# Load environment variables
load_dotenv()


# ============================================================================
# ACTIVITIES - Specialized operations for each agent
# ============================================================================

@activity.defn
async def ai_analyze_task(task: str) -> str:
    """AI analysis activity for AnalyzerAgent."""
    activity.logger.info(f"[AnalyzerAgent] Analyzing: {task}")

    chat_id = str(uuid.uuid4())
    username = os.getenv("TRACE_ADMIN_USER", "admin")
    workflow_id = activity.info().workflow_id
    tracer = trace.get_tracer(__name__)

    try:
        anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        user_prompt = f"Analyze this task and recommend a specific action: {task}"

        with tracer.start_as_current_span("llm.anthropic.messages") as llm_span:
            llm_span.set_attribute("chat.type", "llm-interaction")
            llm_span.set_attribute("chat.id", chat_id)
            llm_span.set_attribute("chat.prompt", user_prompt)
            llm_span.set_attribute("x-username", username)
            llm_span.set_attribute("x-session-id", workflow_id)
            llm_span.set_attribute("trace.entity", "chat-prompt-response")
            response = await anthropic_client.messages.create(
                model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
                max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024")),
                system="""You are a specialized Analysis Agent. Your job is to analyze tasks and recommend specific actions.
Be analytical, thorough, and provide actionable recommendations.""",
                messages=[
                    {
                        "role": "user",
                        "content": user_prompt,
                    }
                ],
            )

            recommendation = response.content[0].text

            llm_span.set_attribute("chat.response", recommendation)
            llm_span.set_attribute("chat.prompt_tokens", response.usage.input_tokens)
            llm_span.set_attribute("chat.completion_tokens", response.usage.output_tokens)
            llm_span.set_attribute("chat.total_tokens", response.usage.input_tokens + response.usage.output_tokens)
            llm_span.set_attribute("chat.model", response.model)

        activity.logger.info(f"[AnalyzerAgent] Recommendation: {recommendation}")
        return recommendation

    except Exception as e:
        activity.logger.error(f"[AnalyzerAgent] Error: {e}")
        return f"Error with AI analysis: {str(e)}"


@activity.defn
async def draft_email_content(task: str, recommendation: str) -> str:
    """Email drafting activity for DrafterAgent."""
    activity.logger.info(f"[DrafterAgent] Drafting email for: {task}")

    chat_id = str(uuid.uuid4())
    username = os.getenv("TRACE_ADMIN_USER", "admin")
    workflow_id = activity.info().workflow_id
    tracer = trace.get_tracer(__name__)

    try:
        anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        user_prompt = f"Task: {task}\n\nRecommendation: {recommendation}\n\nPlease draft a complete email for this task."

        with tracer.start_as_current_span("llm.anthropic.messages") as llm_span:
            llm_span.set_attribute("chat.type", "llm-interaction")
            llm_span.set_attribute("chat.id", chat_id)
            llm_span.set_attribute("chat.prompt", user_prompt)
            llm_span.set_attribute("x-username", username)
            llm_span.set_attribute("x-session-id", workflow_id)
            llm_span.set_attribute("trace.entity", "chat-prompt-response")
            response = await anthropic_client.messages.create(
                model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
                max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024")),
                system="""You are a specialized Email Drafting Agent. Your job is to create professional, well-formatted emails.
Include Subject, To, and Body. Be professional, clear, and concise.""",
                messages=[
                    {
                        "role": "user",
                        "content": user_prompt,
                    }
                ],
            )

            draft = response.content[0].text

            llm_span.set_attribute("chat.response", draft)
            llm_span.set_attribute("chat.prompt_tokens", response.usage.input_tokens)
            llm_span.set_attribute("chat.completion_tokens", response.usage.output_tokens)
            llm_span.set_attribute("chat.total_tokens", response.usage.input_tokens + response.usage.output_tokens)
            llm_span.set_attribute("chat.model", response.model)

        activity.logger.info(f"[DrafterAgent] Email drafted successfully")
        return draft

    except Exception as e:
        activity.logger.error(f"[DrafterAgent] Error: {e}")
        return f"Error drafting email: {str(e)}"


@activity.defn
async def execute_email_action(email_content: str) -> str:
    """Execution activity for ExecutorAgent."""
    activity.logger.info(f"[ExecutorAgent] Executing email send")

    await asyncio.sleep(2)  # Simulate email sending

    activity.logger.info(f"[ExecutorAgent] Email sent successfully")
    return f"Email sent successfully"


# ============================================================================
# AGENT WORKFLOWS - Each agent is a separate workflow
# ============================================================================

@dataclass
class AnalysisRequest:
    task: str


@dataclass
class AnalysisResult:
    recommendation: str
    success: bool


@workflow.defn
class AnalyzerAgent:
    """Specialized agent for analyzing tasks using AI."""

    @workflow.run
    async def run(self, request: AnalysisRequest) -> AnalysisResult:
        workflow.logger.info(f"[AnalyzerAgent] Starting analysis for: {request.task}")

        try:
            recommendation = await workflow.execute_activity(
                ai_analyze_task,
                request.task,
                start_to_close_timeout=timedelta(seconds=60),
            )

            workflow.logger.info(f"[AnalyzerAgent] Analysis complete")
            return AnalysisResult(recommendation=recommendation, success=True)

        except Exception as e:
            workflow.logger.error(f"[AnalyzerAgent] Failed: {e}")
            return AnalysisResult(recommendation=str(e), success=False)


@dataclass
class DraftRequest:
    task: str
    recommendation: str


@dataclass
class DraftResult:
    email_draft: str
    success: bool


@workflow.defn
class DrafterAgent:
    """Specialized agent for drafting emails."""

    @workflow.run
    async def run(self, request: DraftRequest) -> DraftResult:
        workflow.logger.info(f"[DrafterAgent] Starting email draft")

        try:
            email_draft = await workflow.execute_activity(
                draft_email_content,
                args=[request.task, request.recommendation],
                start_to_close_timeout=timedelta(seconds=60),
            )

            workflow.logger.info(f"[DrafterAgent] Draft complete")
            return DraftResult(email_draft=email_draft, success=True)

        except Exception as e:
            workflow.logger.error(f"[DrafterAgent] Failed: {e}")
            return DraftResult(email_draft=str(e), success=False)


@dataclass
class ExecutionRequest:
    email_content: str


@dataclass
class ExecutionResult:
    message: str
    success: bool


@workflow.defn
class ExecutorAgent:
    """Specialized agent for executing actions."""

    @workflow.run
    async def run(self, request: ExecutionRequest) -> ExecutionResult:
        workflow.logger.info(f"[ExecutorAgent] Starting execution")

        try:
            result = await workflow.execute_activity(
                execute_email_action,
                request.email_content,
                start_to_close_timeout=timedelta(seconds=30),
            )

            workflow.logger.info(f"[ExecutorAgent] Execution complete")
            return ExecutionResult(message=result, success=True)

        except Exception as e:
            workflow.logger.error(f"[ExecutorAgent] Failed: {e}")
            return ExecutionResult(message=str(e), success=False)


# ============================================================================
# COORDINATOR AGENT - Orchestrates all other agents
# ============================================================================

@dataclass
class CoordinatorInput:
    task: str
    user_email: str


@workflow.defn
class CoordinatorAgent:
    """Main coordinator that orchestrates all specialized agents with human-in-the-loop."""

    def __init__(self):
        self.recommendation_approved = None
        self.draft_approved = None
        self.analysis_result: Optional[AnalysisResult] = None
        self.draft_result: Optional[DraftResult] = None
        self.run_span_context: Optional[dict] = None

    @workflow.run
    async def run(self, input: CoordinatorInput) -> str:
        # Capture the RunWorkflow span context once so the client can parent
        # human-interaction spans directly under this workflow span.
        if self.run_span_context is None:
            span_ctx = trace.get_current_span().get_span_context()
            if span_ctx.is_valid:
                self.run_span_context = {
                    "trace_id": format(span_ctx.trace_id, "032x"),
                    "span_id": format(span_ctx.span_id, "016x"),
                    "trace_flags": int(span_ctx.trace_flags),
                }

        workflow.logger.info(f"[CoordinatorAgent] Starting coordination for: {input.task}")

        # Step 1: Delegate to AnalyzerAgent
        workflow.logger.info("[CoordinatorAgent] Spawning AnalyzerAgent...")

        self.analysis_result = await workflow.execute_child_workflow(
            AnalyzerAgent.run,
            AnalysisRequest(task=input.task),
            id=f"analyzer-{workflow.info().workflow_id}",
            task_queue="multi-agent-system",
        )

        if not self.analysis_result.success:
            return f"❌ Analysis failed: {self.analysis_result.recommendation}"

        workflow.logger.info(f"[CoordinatorAgent] Analysis complete, waiting for approval...")

        # Step 2: Wait for human approval of recommendation
        await workflow.wait_condition(
            lambda: self.recommendation_approved is not None,
            timeout=timedelta(hours=1)
        )

        if not self.recommendation_approved:
            workflow.logger.info("[CoordinatorAgent] Recommendation rejected")
            return "❌ Recommendation rejected by user. No action taken."

        # Step 3: Delegate to DrafterAgent
        workflow.logger.info("[CoordinatorAgent] Spawning DrafterAgent...")

        self.draft_result = await workflow.execute_child_workflow(
            DrafterAgent.run,
            DraftRequest(task=input.task, recommendation=self.analysis_result.recommendation),
            id=f"drafter-{workflow.info().workflow_id}",
            task_queue="multi-agent-system",
        )

        if not self.draft_result.success:
            return f"❌ Drafting failed: {self.draft_result.email_draft}"

        workflow.logger.info(f"[CoordinatorAgent] Draft complete, waiting for approval...")

        # Step 4: Wait for human approval of draft
        await workflow.wait_condition(
            lambda: self.draft_approved is not None,
            timeout=timedelta(hours=1)
        )

        if not self.draft_approved:
            workflow.logger.info("[CoordinatorAgent] Draft rejected")
            return "❌ Email draft rejected by user. No action taken."

        # Step 5: Delegate to ExecutorAgent
        workflow.logger.info("[CoordinatorAgent] Spawning ExecutorAgent...")

        execution_result = await workflow.execute_child_workflow(
            ExecutorAgent.run,
            ExecutionRequest(email_content=self.draft_result.email_draft),
            id=f"executor-{workflow.info().workflow_id}",
            task_queue="multi-agent-system",
        )

        if not execution_result.success:
            return f"❌ Execution failed: {execution_result.message}"

        workflow.logger.info(f"[CoordinatorAgent] All agents completed successfully")
        return f"✅ {execution_result.message}"

    @workflow.signal
    def approve_recommendation(self):
        workflow.logger.info("[CoordinatorAgent] Recommendation approved by human")
        self.recommendation_approved = True

    @workflow.signal
    def reject_recommendation(self):
        workflow.logger.info("[CoordinatorAgent] Recommendation rejected by human")
        self.recommendation_approved = False

    @workflow.signal
    def approve_draft(self):
        workflow.logger.info("[CoordinatorAgent] Draft approved by human")
        self.draft_approved = True

    @workflow.signal
    def reject_draft(self):
        workflow.logger.info("[CoordinatorAgent] Draft rejected by human")
        self.draft_approved = False

    @workflow.query
    def get_run_span_context(self) -> dict:
        return self.run_span_context or {}

    @workflow.query
    def get_recommendation(self) -> str:
        if self.analysis_result:
            return self.analysis_result.recommendation
        return "No recommendation yet"

    @workflow.query
    def get_draft(self) -> str:
        if self.draft_result:
            return self.draft_result.email_draft
        return "No draft yet"


# ============================================================================
# OPENTELEMETRY SETUP
# ============================================================================

def setup_opentelemetry():
    """Configure OpenTelemetry to export traces to the trace server."""

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

    if not otlp_endpoint:
        trace_server_host = os.getenv("TRACE_SERVER_HOST", "localhost")
        trace_server_port = os.getenv("TRACE_SERVER_PORT", "4517")
        otlp_endpoint = f"{trace_server_host}:{trace_server_port}"
    else:
        otlp_endpoint = otlp_endpoint.replace("http://", "").replace("https://", "")

    ifuser = os.getenv("TRACE_ADMIN_USER", "admin")
    iflicensekey = os.getenv("TRACE_ADMIN_USER_LICENSE", "")
    ifproject = os.getenv("TRACE_PROJECT", "temporal-traces")
    ifsystem = os.getenv("TRACE_SYSTEM", "temporal-system")

    service_name = os.getenv("SERVICE_NAME", "temporal-multi-agent-system")
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.0.0",
    })

    otlp_exporter = OTLPSpanExporter(
        endpoint=otlp_endpoint,
        insecure=True,
        headers=(
            ("ifuser", ifuser),
            ("iflicensekey", iflicensekey),
            ("ifproject", ifproject),
            ("ifsystem", ifsystem),
        ),
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(tracer_provider)

    tracer = trace.get_tracer("temporal-multi-agent", "1.0.0")

    print(f"✅ OpenTelemetry configured to send traces to {otlp_endpoint}")
    print(f"   - User: {ifuser}")
    print(f"   - Project: {ifproject}")
    print(f"   - System: {ifsystem}")

    return tracer


# ============================================================================
# WORKER - Registers all agents and activities
# ============================================================================

async def run_worker_in_background(client):
    """Start the worker that handles all agents."""
    worker = Worker(
        client,
        task_queue="multi-agent-system",
        workflows=[CoordinatorAgent, AnalyzerAgent, DrafterAgent, ExecutorAgent],
        activities=[ai_analyze_task, draft_email_content, execute_email_action],
        workflow_runner=SandboxedWorkflowRunner(
            restrictions=SandboxRestrictions.default.with_passthrough_modules(
                "opentelemetry", "anthropic", "httpx", "httpcore", "dotenv"
            )
        ),
    )

    worker_task = asyncio.create_task(worker.run())
    return worker_task


# ============================================================================
# HELPERS
# ============================================================================

async def ask_approval(prompt: str, interactive: bool) -> tuple[bool, str]:
    """Ask for human approval. If interactive, waits for keyboard input.
    If non-interactive (CI/CD), simulates approval automatically.
    Returns (approved, raw_answer)."""
    print(f"❓ {prompt} (y/n): ", end="", flush=True)
    if interactive:
        answer = await asyncio.get_event_loop().run_in_executor(None, input)
    else:
        await asyncio.sleep(1)
        answer = "y"
        print(f"{answer}  [simulated]")
    return answer.strip().lower() in ("y", "yes"), answer.strip()


def attach_workflow_span_context(span_ctx_data: dict):
    """Attach the workflow's RunWorkflow span as the OTel parent context.
    Returns a token that must be passed to otel_context.detach() after use."""
    if not span_ctx_data.get("trace_id"):
        return None
    span_ctx = SpanContext(
        trace_id=int(span_ctx_data["trace_id"], 16),
        span_id=int(span_ctx_data["span_id"], 16),
        is_remote=True,
        trace_flags=TraceFlags(span_ctx_data.get("trace_flags", 1)),
    )
    return otel_context.attach(trace.set_span_in_context(NonRecordingSpan(span_ctx)))


# ============================================================================
# MAIN - Interactive interface
# ============================================================================

async def main(interactive: bool):
    print("🤖 Multi-Agent AI System with Human-in-the-Loop (Anthropic Claude)")
    print("=" * 60)
    print("Agents:")
    print("  🔍 AnalyzerAgent - Task analysis")
    print("  ✍️  DrafterAgent - Email drafting")
    print("  ⚡ ExecutorAgent - Action execution")
    print("  🎯 CoordinatorAgent - Orchestration")
    print("=" * 60)
    print()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("❌ Error: ANTHROPIC_API_KEY not found!")
        print("\nPlease add to your .env file:")
        print("  ANTHROPIC_API_KEY=your-key-here")
        print("  ANTHROPIC_MODEL=claude-sonnet-4-6")
        sys.exit(1)

    print("🔭 Setting up OpenTelemetry tracing...")
    tracer = setup_opentelemetry()

    print("📡 Connecting to Temporal...")
    try:
        client = await Client.connect(
            "localhost:7233",
            interceptors=[TracingInterceptor(tracer)]
        )
        print("✅ Connected to Temporal server with tracing enabled")
    except Exception as e:
        print(f"❌ Could not connect to Temporal server: {e}")
        print("\nMake sure Temporal is running:")
        print("  temporal server start-dev")
        sys.exit(1)

    print("🔧 Starting multi-agent worker...")
    worker_task = await run_worker_in_background(client)
    print("✅ Worker started (all agents ready)")

    await asyncio.sleep(2)

    print()

    task = "Send email to the team about project status"
    print("📝 Using task: Send email to the team about project status")
    print()

    print()
    print(f"📋 Task: {task}")
    print()

    with tracer.start_as_current_span("CoordinatorAgent"):

        workflow_id = f"coordinator-{int(asyncio.get_event_loop().time())}"
        trace.get_current_span().set_attribute("chat.prompt", task)
        print(f"🎯 Starting CoordinatorAgent...")

        try:
            handle = await client.start_workflow(
                CoordinatorAgent.run,
                CoordinatorInput(task=task, user_email="user@example.com"),
                id=workflow_id,
                task_queue="multi-agent-system",
            )
            print("✅ CoordinatorAgent started!")
            print("🔍 AnalyzerAgent is analyzing your task...")
        except Exception as e:
            print(f"❌ Could not start workflow: {e}")
            worker_task.cancel()
            sys.exit(1)

        # Fetch the RunWorkflow span context from the workflow so human spans
        # can be parented directly under it in the trace tree.
        wf_ctx_data = {}
        for _ in range(10):
            await asyncio.sleep(0.5)
            try:
                wf_ctx_data = await handle.query(CoordinatorAgent.get_run_span_context)
                if wf_ctx_data.get("trace_id"):
                    break
            except Exception:
                pass

        print()

        max_attempts = 15
        recommendation = None

        # Poll outside the span — the span should only open once the recommendation exists
        for attempt in range(max_attempts):
            await asyncio.sleep(5)

            try:
                recommendation = await handle.query(CoordinatorAgent.get_recommendation)

                if recommendation and recommendation != "No recommendation yet":
                    break
                else:
                    if attempt % 3 == 0 and attempt > 0:
                        print("⏳ AnalyzerAgent still working...")

            except Exception as e:
                if attempt < max_attempts - 1:
                    continue
                else:
                    print(f"❌ Error: {e}")
                    worker_task.cancel()
                    sys.exit(1)

        if not recommendation or recommendation == "No recommendation yet":
            print("❌ AnalyzerAgent did not complete in time")
            worker_task.cancel()
            sys.exit(1)

        # Recommendation is ready — open the review span now so it starts after AnalyzerAgent
        token = attach_workflow_span_context(wf_ctx_data)
        try:
            with tracer.start_as_current_span("human.review_recommendation"):

                print()
                print("🔍 AnalyzerAgent Recommendation:")
                print("-" * 60)
                print(recommendation)
                print("-" * 60)
                print()

                with tracer.start_as_current_span("human.approve_recommendation") as approval_span:
                    approved, raw_answer = await ask_approval(interactive=interactive, prompt="Approve this recommendation?")
                    approval_span.set_attribute("chat.prompt", raw_answer)
                    approval_span.set_attribute("human.input", True)
                    if approved:
                        await handle.signal(CoordinatorAgent.approve_recommendation)
                        print("✅ Approved! Delegating to DrafterAgent...")
                    else:
                        await handle.signal(CoordinatorAgent.reject_recommendation)
                        print("❌ Rejected! Workflow will stop.")
        finally:
            if token:
                otel_context.detach(token)

        if not approved:
            return

        print()
        print("⏳ DrafterAgent is creating email draft...")

        max_attempts = 15
        email_draft = None

        # Poll outside the span — the span should only open once the draft exists
        for attempt in range(max_attempts):
            await asyncio.sleep(5)

            try:
                email_draft = await handle.query(CoordinatorAgent.get_draft)

                if email_draft and email_draft != "No draft yet":
                    break
                else:
                    if attempt % 3 == 0 and attempt > 0:
                        print("⏳ DrafterAgent still working...")

            except Exception as e:
                if attempt < max_attempts - 1:
                    continue
                else:
                    print(f"❌ Error: {e}")
                    worker_task.cancel()
                    sys.exit(1)

        if not email_draft or email_draft == "No draft yet":
            print("❌ DrafterAgent did not complete in time")
            worker_task.cancel()
            sys.exit(1)

        # Draft is ready — open the review span now so it starts after DrafterAgent
        token = attach_workflow_span_context(wf_ctx_data)
        try:
            with tracer.start_as_current_span("human.review_draft"):

                print()
                print("✍️  DrafterAgent Email Draft:")
                print("=" * 60)
                print(email_draft)
                print("=" * 60)
                print()

                with tracer.start_as_current_span("human.approve_draft") as approval_span:
                    approved, raw_answer = await ask_approval(interactive=interactive, prompt="Approve this email draft?")
                    approval_span.set_attribute("chat.prompt", raw_answer)
                    approval_span.set_attribute("human.input", True)
                    if approved:
                        await handle.signal(CoordinatorAgent.approve_draft)
                        print("✅ Email approved! Delegating to ExecutorAgent...")
                    else:
                        await handle.signal(CoordinatorAgent.reject_draft)
                        print("❌ Rejected! Workflow will stop.")
        finally:
            if token:
                otel_context.detach(token)

        if not approved:
            return

        try:
            result = await asyncio.wait_for(handle.result(), timeout=60)
            print()
            print("🎉 Multi-Agent System Complete!")
            print(result)
        except asyncio.TimeoutError:
            print("⏳ Execution taking longer than expected...")
        except Exception as e:
            print(f"❌ Error: {e}")

    print()
    print("👋 Done! Shutting down multi-agent system...")

    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--interactive",
        choices=["yes", "no"],
        default="no",
        help="yes: prompt for human approval; no: simulate approval automatically",
    )
    args = parser.parse_args()
    try:
        asyncio.run(main(interactive=args.interactive == "yes"))
    except KeyboardInterrupt:
        print("\n\n👋 Cancelled by user")
        sys.exit(0)
