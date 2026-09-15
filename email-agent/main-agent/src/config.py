from pydantic import Field
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional
import os

# Resolve email-agent/.env regardless of which directory the service is started from.
# Layout: email-agent/main-agent/src/config.py -> 2 levels up = email-agent/
_AGENT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ENV_FILE = os.path.join(_AGENT_ROOT, ".env")


class Settings(BaseSettings):
    """Main Agent Service configuration."""

    service_name: str = "main-agent"
    host: str = "0.0.0.0"
    http_port: int = 8007

    # Temporal. Distinct env var prefix so this doesn't collide with any
    # other service's TEMPORAL_* in the same repo-root .env (same reasoning
    # as github-agent's ONCALL_TEMPORAL_* fields).
    temporal_address: str = Field(default="localhost:7233", validation_alias="MAIN_AGENT_TEMPORAL_ADDRESS")
    temporal_namespace: str = Field(default="default", validation_alias="MAIN_AGENT_TEMPORAL_NAMESPACE")
    temporal_task_queue: str = Field(default="main-agent-queue", validation_alias="MAIN_AGENT_TEMPORAL_TASK_QUEUE")

    # The email-subagent's own Service address -- a different Pod, called
    # over HTTP (in-cluster DNS in production, localhost when run locally).
    subagent_url: str = Field(default="http://localhost:8008", validation_alias="EMAIL_SUBAGENT_URL")

    # Real SMTP send (no longer mocked). smtplib (stdlib) + SSL, matching
    # the account this was first tested against (NetEase yeah.net: smtp.yeah.net:465).
    smtp_host: str = Field(default="smtp.yeah.net", validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=465, validation_alias="SMTP_PORT")
    smtp_username: Optional[str] = Field(default=None, validation_alias="SMTP_USERNAME")
    smtp_password: Optional[str] = Field(default=None, validation_alias="SMTP_PASSWORD")
    smtp_from: Optional[str] = Field(default=None, validation_alias="SMTP_FROM")

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
