#!/usr/bin/env python3
"""
Datadog Trace Streaming to InsightFinder.

Reads all YAML configs from conf.d/, queries Datadog spans for each trace
filter, and forwards the results to InsightFinder as log-streaming data.

Designed to be triggered repeatedly by a Linux cron job, e.g.:
    * * * * * /path/to/.venv/bin/python /path/to/main.py

"""

import http.client
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

from insightfinder import send_log_data_to_if

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("dd-trace-stream")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_DD_ENDPOINT = "https://api.datadoghq.com"
DEFAULT_LOOKBACK_MINUTES = 60
DEFAULT_LIMIT = 2000
IF_BATCH_SIZE = 500  # max log entries per InsightFinder request


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def load_configs(conf_dir: str) -> list[dict]:
    """Return all valid YAML configs found under *conf_dir*."""
    p = Path(conf_dir)
    if not p.is_dir():
        log.error("conf.d directory not found: %s", conf_dir)
        return []

    configs: list[dict] = []
    for yaml_file in sorted(p.glob("*.yaml")):
        try:
            with open(yaml_file) as fh:
                cfg = yaml.safe_load(fh)
            if cfg and isinstance(cfg, dict):
                cfg["_source"] = str(yaml_file)
                configs.append(cfg)
                log.info("Loaded config: %s", yaml_file)
            else:
                log.warning("Skipping empty or invalid config: %s", yaml_file)
        except Exception as exc:
            log.error("Failed to load %s: %s", yaml_file, exc)

    return configs


# ---------------------------------------------------------------------------
# Datadog span fetching
# ---------------------------------------------------------------------------


def fetch_spans(
    *,
    api_key: str,
    app_key: str,
    query: str,
    start: datetime,
    end: datetime,
    limit: int,
    base_url: str,
) -> list[dict]:
    """Query the Datadog Spans Search API and return a list of span objects."""
    body = {
        "data": {
            "type": "search_request",
            "attributes": {
                "filter": {
                    "from": start.isoformat(),
                    "to": end.isoformat(),
                    "query": query,
                },
                "page": {"limit": limit},
                "sort": "-timestamp",
            },
        }
    }

    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v2/spans/events/search",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "DD-API-KEY": api_key,
            "DD-APPLICATION-KEY": app_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode()).get("data", [])
    except urllib.error.HTTPError as exc:
        log.error("Datadog API HTTP %d: %s", exc.code, exc.read().decode())
    except urllib.error.URLError as exc:
        log.error("Datadog API network error: %s", exc)

    return []


# ---------------------------------------------------------------------------
# Span → InsightFinder entry transformation
# ---------------------------------------------------------------------------


def _parse_timestamp_ms(ts: Any) -> int:
    """Convert a Datadog timestamp value to epoch milliseconds."""
    if isinstance(ts, (int, float)):
        # Could be seconds or milliseconds; treat values > 1e12 as ms
        return int(ts) if ts > 1e12 else int(ts * 1000)
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1000)
        except ValueError:
            pass
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def span_to_if_entry(span: dict, instance_name_field: str) -> dict[str, Any]:
    """Convert one Datadog span dict to an InsightFinder log-streaming entry.

    InsightFinder schema:
        timestamp     – epoch milliseconds
        tag           – instance / host identifier
        componentName – logical component (service name)
        data          – arbitrary dict payload
    """
    attrs: dict = span.get("attributes", {})
    span_tags: dict = attrs.get("tags", {})

    ts_ms = _parse_timestamp_ms(attrs.get("timestamp"))

    # Resolve instance name: check span attributes then span tags, else fall
    # back to service name or the span id.
    tag = ""
    if instance_name_field:
        tag = (
            attrs.get(instance_name_field)
            or span_tags.get(instance_name_field)
            or ""
        )
    if not tag:
        tag = attrs.get("service") or span.get("id", "unknown")

    tag = tag.replace("_", "-")
    component = attrs.get("service", "unknown")

    return {
        "timestamp": ts_ms,
        "tag": str(tag),
        "componentName": str(component),
        "data": {
            "span_id": span.get("id", ""),
            **attrs,
        },
    }


# ---------------------------------------------------------------------------
# Send batches to InsightFinder
# ---------------------------------------------------------------------------


def send_to_insightfinder(
    *,
    if_url: str,
    if_user: str,
    if_key: str,
    if_project: str,
    metric_data: list[dict],
    source: str,
) -> None:
    """Send *metric_data* to InsightFinder in batches of IF_BATCH_SIZE."""
    total = len(metric_data)
    sent = 0

    for offset in range(0, total, IF_BATCH_SIZE):
        batch = metric_data[offset : offset + IF_BATCH_SIZE]
        try:
            resp = send_log_data_to_if(
                user_name=if_user,
                project_name=if_project,
                license_key=if_key,
                metric_data=batch,
                system_name=if_project,
                if_url=if_url,
            )
            sent += len(batch)
            log.info(
                "[%s] Sent %d/%d entries to InsightFinder | response: %s",
                source,
                sent,
                total,
                resp,
            )
        except requests.HTTPError as exc:
            log.error(
                "[%s] InsightFinder HTTP %d: %s",
                source,
                exc.response.status_code,
                exc.response.text,
            )
        except requests.ConnectionError as exc:
            log.error("[%s] InsightFinder network error: %s", source, exc)


# ---------------------------------------------------------------------------
# Per-config processing
# ---------------------------------------------------------------------------


def process_config(cfg: dict) -> None:
    source: str = cfg.get("_source", "unknown")

    dd: dict = cfg.get("datadog") or {}
    if_cfg: dict = cfg.get("insightfinder") or {}
    agent_cfg: dict = cfg.get("agent") or {}

    # ── Datadog credentials ──────────────────────────────────────────────────
    api_key: str = dd.get("api_key") or ""
    app_key: str = dd.get("application_key") or ""
    base_url: str = dd.get("endpoint") or DEFAULT_DD_ENDPOINT
    lookback: int = int(agent_cfg.get("lookback") or DEFAULT_LOOKBACK_MINUTES)
    limit: int = int(agent_cfg.get("limit") or DEFAULT_LIMIT)

    if not api_key or not app_key:
        log.error("[%s] Missing Datadog api_key or application_key — skipping", source)
        return

    # ── InsightFinder credentials ────────────────────────────────────────────
    if_url: str = if_cfg.get("url") or ""
    if_user: str = if_cfg.get("username") or ""
    if_key: str = if_cfg.get("license_key") or ""
    if_project: str = if_cfg.get("project") or ""

    if not all([if_url, if_user, if_key, if_project]):
        log.error("[%s] Incomplete InsightFinder config — skipping", source)
        return

    # ── Trace query configs ──────────────────────────────────────────────────
    trace_configs: list[dict] = dd.get("trace") or []
    if not trace_configs:
        log.warning("[%s] No trace queries defined — skipping", source)
        return

    # Compute the time window once so all queries share the same start/end,
    # regardless of how long individual fetch operations take.
    query_end: datetime = datetime.now(timezone.utc)
    query_start: datetime = query_end - timedelta(minutes=lookback)

    for tc in trace_configs:
        raw_queries = tc.get("query") or []
        instance_name_field: str = tc.get("instance_name_field") or ""

        # query may be a list of filter strings (ANDed together) or a single string
        if isinstance(raw_queries, list):
            query_str = " ".join(q for q in raw_queries if q).strip() or "*"
        elif raw_queries:
            query_str = str(raw_queries).strip()
        else:
            query_str = "*"

        log.info(
            "[%s] Fetching spans | query=%r lookback=%dm limit=%d",
            source,
            query_str,
            lookback,
            limit,
        )

        spans = fetch_spans(
            api_key=api_key,
            app_key=app_key,
            query=query_str,
            start=query_start,
            end=query_end,
            limit=limit,
            base_url=base_url,
        )

        log.info("[%s] Received %d span(s) from Datadog", source, len(spans))
        if not spans:
            continue

        metric_data = [span_to_if_entry(s, instance_name_field) for s in spans]

        send_to_insightfinder(
            if_url=if_url,
            if_user=if_user,
            if_key=if_key,
            if_project=if_project,
            metric_data=metric_data,
            source=source,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


CONF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conf.d")


def main() -> None:
    configs = load_configs(CONF_DIR)
    if not configs:
        log.error("No configs loaded from %s — exiting", CONF_DIR)
        sys.exit(1)

    log.info("Processing %d config file(s)", len(configs))
    for cfg in configs:
        try:
            process_config(cfg)
        except Exception:
            log.exception("Unhandled error processing %s", cfg.get("_source"))


if __name__ == "__main__":
    main()
