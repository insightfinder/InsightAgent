"""
OpenTelemetry Tracing Initialization

Provides a thin wrapper to initialize distributed tracing
across all services with consistent configuration.
"""

import os
from typing import Optional

import structlog

logger = structlog.get_logger()


def init_tracing(
    service_name: str,
    otlp_endpoint: Optional[str] = None,
    enable_console: bool = False,
    headers: Optional[dict] = None,
):
    """
    Initialize OpenTelemetry tracing for a service.

    Args:
        service_name: Name of the service (e.g., "api-gateway").
        otlp_endpoint: OTLP gRPC endpoint (default: localhost:4317). Comma-
            separated for more than one -- a separate exporter/processor is
            added per endpoint, so the same spans fan out to every one of
            them (e.g. sending to all 4 traceserver instances at once while
            it's unclear which one InsightFinder's own UI actually reads).
        enable_console: Also print spans to console (dev mode).
        headers: Extra gRPC metadata headers sent with every export batch.
            InsightFinder's own traceserver (unlike a generic OTLP collector)
            requires identity headers (ifuser/ifproject/ifsystem/iflicensekey,
            all lowercase) on every batch or it silently drops the trace
            server-side -- see GrpcTraceService.java in
            OpenTelemetryService-Trace. Optional so existing callers that
            don't need this (e.g. a plain collector) are unaffected.

    Returns:
        A Tracer instance for creating spans.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.semconv.resource import ResourceAttributes
    except ImportError:
        logger.warning(
            "OpenTelemetry SDK not installed. Tracing disabled.",
            hint="pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc",
        )
        return None

    endpoint_str = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    endpoints = [e.strip() for e in endpoint_str.split(",") if e.strip()]

    resource = Resource.create({
        ResourceAttributes.SERVICE_NAME: service_name,
        ResourceAttributes.SERVICE_VERSION: os.getenv("SERVICE_VERSION", "0.1.0"),
        ResourceAttributes.DEPLOYMENT_ENVIRONMENT: os.getenv("ENVIRONMENT", "development"),
    })

    provider = TracerProvider(resource=resource)

    # OTLP exporter(s) (Jaeger / Tempo / Collector / traceserver) -- one
    # BatchSpanProcessor per endpoint, so the same spans fan out to all of
    # them independently (a failure exporting to one doesn't affect the others).
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        for ep in endpoints:
            # insecure=True: every OTLP target in this repo (traceserver
            # included) is plaintext gRPC, never TLS -- without this the
            # exporter attempts a TLS handshake and every export silently fails.
            otlp_exporter = OTLPSpanExporter(endpoint=ep, insecure=True, headers=headers)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info("OTLP trace exporter configured", endpoint=ep)
    except ImportError:
        logger.warning(
            "OTLP exporter not available",
            hint="pip install opentelemetry-exporter-otlp-proto-grpc",
        )

    # Console exporter (development)
    if enable_console:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(service_name)

    logger.info("OpenTelemetry tracing initialized", service=service_name)
    return tracer


def instrument_httpx(service_name: str):
    """
    Auto-instrument outgoing httpx requests, so every client call injects a
    `traceparent` header and the receiving service continues the SAME trace
    instead of starting a new one.

    Separate from instrument_fastapi() because a process can need this
    without serving HTTP at all: a Temporal worker makes the cross-service
    calls from inside activities, and without this its spans and the callee's
    end up under two unrelated trace IDs -- which breaks any multi-component
    view that groups spans by trace.
    """
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
        logger.info("httpx auto-instrumented", service=service_name)
    except ImportError:
        logger.debug("httpx instrumentation not available")


def instrument_fastapi(app, service_name: str):
    """
    Auto-instrument a FastAPI application with OpenTelemetry.

    Instruments:
    - Incoming HTTP requests (FastAPI)
    - Outgoing HTTP requests (httpx)
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        # Kubernetes liveness/readiness probes hit /health every few seconds;
        # each one would otherwise become its own trace and get shipped to
        # traceserver, burying the real traces in noise.
        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,healthz,metrics")
        logger.info("FastAPI auto-instrumented", service=service_name)
    except ImportError:
        logger.debug("FastAPI instrumentation not available")

    instrument_httpx(service_name)


def get_current_trace_context() -> dict:
    """
    Extract current trace/span IDs for correlation.

    Returns:
        Dict with trace_id and span_id (empty strings if no active span).
    """
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            return {
                "trace_id": format(ctx.trace_id, "032x"),
                "span_id": format(ctx.span_id, "016x"),
            }
    except Exception:
        pass

    return {"trace_id": "", "span_id": ""}
