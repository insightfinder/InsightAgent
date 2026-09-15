"""
Activity backing SubagentDraftWorkflow.

This is the one real model call in the demo (per review feedback: the
trace sent to traceserver needs actual LLM-call structure -- prompt/
response/tokens -- to be meaningful to AW, not just Temporal plumbing
wrapping deterministic string formatting). Calls Claude Haiku directly via
the Anthropic SDK.

The Temporal-interceptor span around this whole activity is "server"-kind
and carries no prompt/response content -- traceserver's promptExtraction
config (both the llm-labs and genai instances) only looks at spans it can
positively identify as an LLM generation step, matched by span.kind=internal
plus specific attribute names. So this manually opens its OWN child span
("generate_answer", kind=INTERNAL) around just the Anthropic call and
stamps it with the attribute conventions traceserver actually reads --
mirrors insightfinder-mcp-service's own Tracer.py (set_span_token_attributes/
set_span_identity_attributes), which is the one already-working reference
for this in the codebase:
  - chat.prompt / chat.response: llm-labs' attrMapping.promptExtraction
    (fieldPath tags.chat.prompt / tags.chat.response) reads these directly.
  - traceloop.entity.input / traceloop.entity.output (as {"inputs"/
    "outputs": text} JSON) + iftracer.entity.name="generate_answer":
    genai's attrMapping instead keys off these (processPath
    tags.iftracer.entity.name, fieldPath tags.traceloop.entity.*).
  - chat.prompt_tokens / chat.response_tokens / chat.total_tokens /
    chat.model: read by the Java backend's MetricJsonParser for cost/usage
    dashboards, independent of which attrMapping variant applies.
Setting both conventions on the same span costs nothing and maximizes the
chance of landing on whichever traceserver instance AW's UI actually reads.
"""
import asyncio
import json
from typing import Optional

import structlog
from anthropic import AsyncAnthropic
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from temporalio import activity

from ..config import get_settings

logger = structlog.get_logger()

SYSTEM_PROMPT = (
    "You are a professional email-drafting assistant. You are given the "
    "recipient's email address, the exact subject line to use, and a "
    "description of what the email should say. Write a complete, polished "
    "email. The first line must be \"Subject: \" followed by the given "
    "subject line, reproduced verbatim -- do not reword or embellish it. "
    "Then a blank line, then the body. Output nothing else -- no preamble, "
    "no commentary."
)

tracer = trace.get_tracer(__name__)


def _client(settings) -> AsyncAnthropic:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def _text_of(response) -> str:
    return "".join(block.text for block in response.content if block.type == "text").strip()


def _set_prompt_response_attributes(span, prompt: str, response: str, model: str,
                                     input_tokens: int, output_tokens: int, settings) -> None:
    # llm-labs schema
    span.set_attribute("chat.prompt", prompt)
    span.set_attribute("chat.response", response)
    # genai schema (Traceloop/OpenLLMetry convention)
    span.set_attribute("iftracer.entity.name", "generate_answer")
    span.set_attribute("traceloop.entity.input", json.dumps({"inputs": prompt}))
    span.set_attribute("traceloop.entity.output", json.dumps({"outputs": response}))
    # Token/model usage -- read by the Java backend's cost/usage dashboards
    # regardless of which attrMapping variant applies (mirrors
    # insightfinder-mcp-service's Tracer.set_span_token_attributes).
    total = input_tokens + output_tokens
    span.set_attribute("chat.prompt_tokens", input_tokens)
    span.set_attribute("chat.response_tokens", output_tokens)
    span.set_attribute("chat.completion_tokens", output_tokens)
    span.set_attribute("chat.total_tokens", total)
    span.set_attribute("chat.model", model)
    # Identity, redundant with the gRPC metadata headers (mirrors
    # insightfinder-mcp-service's Tracer.set_span_identity_attributes) --
    # some attrMapping variants read username off the span instead.
    span.set_attribute("chat.username", settings.if_trace_user)
    span.set_attribute("x-username", settings.if_trace_user)
    span.set_attribute("x-licensekey", settings.if_trace_license_key)
    span.set_attribute("x-trace-project", settings.if_trace_project)


@activity.defn
async def draft_email_activity(to_email: str, subject: str, brief: str,
                               model: Optional[str] = None) -> dict:
    settings = get_settings()
    client = _client(settings)
    user_message = (
        f"Recipient: {to_email}\n"
        f"Subject line to use verbatim: {subject}\n\n"
        f"What the email should say: {brief}"
    )
    model_name = model or settings.default_model

    # Stretch this activity's span so the workflow's latency is visible
    # on AW's trace view; the model call alone is far too fast to read.
    # Slept inside the activity rather than as a workflow timer so the
    # duration lands on a span that actually gets exported. Every timeout
    # down the call chain is sized around this value.
    if settings.draft_delay_seconds > 0:
        logger.info("draft_email_activity pausing before draft",
                    delay_seconds=settings.draft_delay_seconds)
        await asyncio.sleep(settings.draft_delay_seconds)

    with tracer.start_as_current_span("generate_answer", kind=SpanKind.INTERNAL) as span:
        response = await client.messages.create(
            model=model_name,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        draft = _text_of(response)
        _set_prompt_response_attributes(
            span, prompt=user_message, response=draft, model=response.model,
            input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
            settings=settings,
        )

    logger.info(
        "draft_email_activity completed (real Claude Haiku call)",
        draft_chars=len(draft),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        model=response.model,
    )
    return {"draft": draft}
