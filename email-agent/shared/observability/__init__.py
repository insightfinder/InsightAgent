"""OpenTelemetry setup shared by main-agent and email-subagent."""

from .tracing import (
    init_tracing,
    instrument_fastapi,
    instrument_httpx,
    get_current_trace_context,
)

__all__ = [
    "init_tracing",
    "instrument_fastapi",
    "instrument_httpx",
    "get_current_trace_context",
]
