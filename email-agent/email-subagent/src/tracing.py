"""
Thin glue between this service's Settings and shared/observability/tracing.py.

Both main.py (API process) and worker.py (Temporal worker process) need to
call init_tracing() once, with the same InsightFinder identity headers --
this is the one place that mapping lives, so the two processes can't drift.
"""
import os
import sys

# Add email-agent/ (2 levels up from email-subagent/src) to
# sys.path, not shared/ itself -- `shared` must resolve as a package one
# level below this entry (email-agent/shared/observability/...), not be the
# entry itself.
_AGENT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _AGENT_ROOT)

from shared.observability.tracing import init_tracing, instrument_fastapi  # noqa: E402

from .config import Settings  # noqa: E402


def setup_tracing(settings: Settings, process_name: str):
    """Initialize tracing for one process. Returns the Tracer, or None if disabled."""
    if not settings.enable_tracing:
        return None
    return init_tracing(
        process_name,
        settings.otlp_endpoint,
        headers={
            "ifuser": settings.if_trace_user,
            "ifproject": settings.if_trace_project,
            "ifsystem": settings.if_trace_system,
            "iflicensekey": settings.if_trace_license_key,
        },
    )


__all__ = ["setup_tracing", "instrument_fastapi"]
