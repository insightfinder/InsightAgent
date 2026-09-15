from pydantic import Field
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional
import os

# Resolve email-agent/.env regardless of which directory the service is started from.
# Layout: email-agent/email-subagent/src/config.py -> 2 levels up = email-agent/
_AGENT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ENV_FILE = os.path.join(_AGENT_ROOT, ".env")


class Settings(BaseSettings):
    """Email Subagent Service configuration."""

    service_name: str = "email-subagent"
    host: str = "0.0.0.0"
    http_port: int = 8008

    # Temporal. Distinct env var prefix so this doesn't collide with any
    # other service's TEMPORAL_* in the same repo-root .env (same reasoning
    # as github-agent's ONCALL_TEMPORAL_* fields).
    temporal_address: str = Field(default="localhost:7233", validation_alias="EMAIL_SUBAGENT_TEMPORAL_ADDRESS")
    temporal_namespace: str = Field(default="default", validation_alias="EMAIL_SUBAGENT_TEMPORAL_NAMESPACE")
    temporal_task_queue: str = Field(default="email-subagent-queue", validation_alias="EMAIL_SUBAGENT_TEMPORAL_TASK_QUEUE")

    # LLM. This subagent's whole point is to demonstrate tracing a real
    # model call (per II-24784 review feedback: the trace needs actual LLM
    # call structure to be meaningful to AW, not just Temporal plumbing).
    anthropic_api_key: Optional[str] = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    default_model: str = Field(default="claude-haiku-4-5-20251001", validation_alias="EMAIL_SUBAGENT_DEFAULT_MODEL")

    # Artificial pause before drafting. The real Haiku call takes ~1.5s,
    # which is too short to read as latency on AW's trace view -- this
    # stretches the activity span so the workflow's timing is legible.
    # Demo-only; every timeout down the call chain is sized around it.
    draft_delay_seconds: int = Field(default=90, validation_alias="EMAIL_SUBAGENT_DRAFT_DELAY_SECONDS")

    # Tracing -- sent to InsightFinder's own traceserver, not a generic collector.
    enable_tracing: bool = Field(default=True, validation_alias="ENABLE_TRACING")
    otlp_endpoint: str = Field(default="http://localhost:4618", validation_alias="OTLP_ENDPOINT")
    if_trace_user: str = Field(default="demoUser", validation_alias="IF_TRACE_USER")
    if_trace_project: str = Field(default="email-demo", validation_alias="IF_TRACE_PROJECT")
    if_trace_system: str = Field(default="ActionAIAgent", validation_alias="IF_TRACE_SYSTEM")
    if_trace_license_key: str = Field(default="", validation_alias="IF_TRACE_LICENSE_KEY")

    model_config = {
        "extra": "ignore",
        "env_file": _ENV_FILE,
        "env_file_encoding": "utf-8",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
