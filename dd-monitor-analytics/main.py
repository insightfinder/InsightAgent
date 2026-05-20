#!/usr/bin/env python3
"""
Datadog Monitors → InsightFinder metric streaming.

Each monitor in conf.d/*.yaml is treated as a metric definition. On every
cron tick the agent:

  1. Executes the monitor's underlying Datadog query (no threshold applied)
  2. Streams the resulting per-bucket timeseries to InsightFinder as a metric
     named after the monitor

Cron usage:
    */5 * * * * /path/to/venv/bin/python /path/to/main.py
"""

import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

from dd_queries import DEFAULT_GROUP_LIMIT, DEFAULT_INTERVAL_SECONDS, execute_monitor_query
from insightfinder import check_and_create_project, send_metric_data_to_if

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("dd-trace-monitor")

DEFAULT_DD_ENDPOINT = "https://api.datadoghq.eu"
DEFAULT_LOOKBACK_MINUTES = 5
DEFAULT_SAMPLING_INTERVAL = 60
IF_BATCH_SIZE = 500

_NON_METRIC_CHARS = re.compile(r"[^A-Za-z0-9_]+")

# Single-facet instance-name sanitiser. `_` and `,` get reserved for the
# group-by join — we want `_` to mean "between facets" so we map any literal
# `_` inside a facet value to `-`.
_INST_UNDERSCORE = re.compile(r"_+")
_INST_SPACE = re.compile(r"\s+")
_INST_COLON = re.compile(r":+")
_INST_LBRACE = re.compile(r"\[")
_INST_RBRACE = re.compile(r"\]")

GROUP_JOIN = "_"


def sanitize_metric_name(name: str) -> str:
    cleaned = _NON_METRIC_CHARS.sub("_", name).strip("_")
    return cleaned or "monitor_value"


def make_safe_instance_string(instance: str) -> str:
    """
    Sanitise a single facet value or static instance name.
    `_` becomes `-` (we use `_` as the group-by join separator).
    """
    instance = _INST_UNDERSCORE.sub("-", instance)
    instance = _INST_SPACE.sub("-", instance)
    instance = _INST_COLON.sub("-", instance)
    instance = _INST_LBRACE.sub("(", instance)
    instance = _INST_RBRACE.sub(")", instance)
    return instance


def load_configs(conf_dir: str) -> list[dict]:
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


def process_monitor(
    *,
    monitor: dict,
    api_key: str,
    app_key: str,
    base_url: str,
    start: datetime,
    end: datetime,
    interval_seconds: int,
    rolling_window_seconds: int | None,
    group_limit: int,
    default_component: str | None,
) -> list[dict]:
    if monitor.get("enabled") is False:
        log.info("→ Monitor %r is disabled — skipping", monitor.get("name"))
        return []

    name = monitor.get("name") or "unnamed_monitor"
    mtype = monitor.get("type") or "query alert"
    query = monitor.get("query") or ""
    metric_name = sanitize_metric_name(monitor.get("metric_name") or name)
    instance_name = monitor.get("instance_name")  # fixed name, ignored if grouped
    component = monitor.get("component_name") or default_component

    # per-monitor overrides for bucket width and rolling window
    mon_interval = int(monitor.get("interval_seconds") or interval_seconds)
    mon_rolling = monitor.get("rolling_window_seconds", rolling_window_seconds)
    mon_rolling = int(mon_rolling) if mon_rolling is not None else None
    mon_group_limit = int(monitor.get("group_limit") or group_limit)

    # Structured trace-analytics fields — an alternative to `query:`. If `filter`
    # is present we skip DSL parsing entirely and build the request from these.
    structured_filter = monitor.get("filter")
    parsed_query: dict | None = None
    if structured_filter is not None:
        parsed_query = {
            "filter": structured_filter,
            "indexes": monitor.get("indexes") or [],
            "aggregator": monitor.get("aggregator") or "count",
            "rollup_metric": monitor.get("rollup_metric"),
            "group_by": monitor.get("group_by") or [],
        }

    if not query and not parsed_query:
        log.warning("Monitor %r has neither 'query' nor 'filter' — skipping", name)
        return []

    log.info("→ Monitor %r (type=%s) metric=%s interval=%ss rolling=%s mode=%s",
             name, mtype, metric_name, mon_interval,
             f"{mon_rolling}s" if mon_rolling else "off",
             "structured" if parsed_query else "query-string")
    series = execute_monitor_query(
        monitor_type=mtype,
        monitor_query=query or None,
        parsed_query=parsed_query,
        api_key=api_key,
        app_key=app_key,
        base_url=base_url,
        start=start,
        end=end,
        interval_seconds=mon_interval,
        rolling_window_seconds=mon_rolling,
        group_limit=mon_group_limit,
    )

    if not series:
        log.info("  no series returned")
        return []

    rows: list[dict] = []
    # If instance_name is set it ALWAYS wins, even when group_by produces
    # multiple groups. In that case all groups collapse into the same instance
    # and per-timestamp values will overwrite each other — log a warning so
    # the lossy behaviour isn't a silent surprise.
    if instance_name and len(series) > 1:
        log.warning(
            "    instance_name=%r overrides %d group_by groups — values will collapse "
            "into one instance (later groups overwrite earlier ones at the same timestamp)",
            instance_name, len(series),
        )

    for group_key, pts in series.items():
        if instance_name:
            resolved_instance = make_safe_instance_string(instance_name)
        elif group_key in ("", "_combined"):
            resolved_instance = make_safe_instance_string(metric_name)
        else:
            # group_key is the comma-joined facet values (e.g. "hybris_/f,GET /foo").
            # Sanitise each facet value independently, then join with GROUP_JOIN.
            resolved_instance = GROUP_JOIN.join(
                make_safe_instance_string(v) for v in group_key.split(",")
            )
        values = [v for _, v in pts]
        peak = max(values) if values else 0.0
        non_zero = sum(1 for v in values if v > 0)
        log.info("    instance=%r points=%d peak=%.2f non_zero=%d",
                 resolved_instance, len(pts), peak, non_zero)
        for ts_ms, value in pts:
            rows.append({
                "instanceName": resolved_instance,
                "componentName": component,
                "timestamp": ts_ms,
                metric_name: value,
            })
    return rows


def process_config(cfg: dict) -> None:
    source: str = cfg.get("_source", "unknown")

    dd: dict = cfg.get("datadog") or {}
    if_cfg: dict = cfg.get("insightfinder") or {}
    agent_cfg: dict = cfg.get("agent") or {}

    api_key: str = dd.get("api_key") or ""
    app_key: str = dd.get("application_key") or ""
    base_url: str = dd.get("endpoint") or DEFAULT_DD_ENDPOINT
    default_component: str | None = dd.get("default_component_name") or None

    if not api_key or not app_key:
        log.error("[%s] Missing Datadog api_key or application_key — skipping", source)
        return

    if_url: str = if_cfg.get("url") or ""
    if_user: str = if_cfg.get("username") or ""
    if_key: str = if_cfg.get("license_key") or ""
    if_project: str = if_cfg.get("project") or ""
    if_system: str = if_cfg.get("system_name") or if_project

    if not all([if_url, if_user, if_key, if_project]):
        log.error("[%s] Incomplete InsightFinder config — skipping", source)
        return

    lookback: int = int(agent_cfg.get("lookback") or DEFAULT_LOOKBACK_MINUTES)
    sampling_interval: int = int(agent_cfg.get("sampling_interval") or DEFAULT_SAMPLING_INTERVAL)
    interval_seconds: int = int(agent_cfg.get("interval_seconds") or DEFAULT_INTERVAL_SECONDS)
    rolling_window_seconds = agent_cfg.get("rolling_window_seconds")
    rolling_window_seconds = int(rolling_window_seconds) if rolling_window_seconds is not None else None
    group_limit: int = int(agent_cfg.get("group_limit") or DEFAULT_GROUP_LIMIT)
    query_offset_minutes: int = int(agent_cfg.get("query_offset_minutes") or 0)

    historic_range: str = agent_cfg.get("historic_time_range") or ""
    historic_chunk_minutes: int = int(agent_cfg.get("historic_chunk_minutes") or 60)

    if historic_range:
        try:
            start_str, end_str = [s.strip() for s in historic_range.split(",", 1)]
            range_start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            range_end   = datetime.strptime(end_str,   "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            log.error("[%s] Invalid historic_time_range (expected 'YYYY-MM-DD HH:MM:SS,YYYY-MM-DD HH:MM:SS')", source)
            return
        windows: list[tuple[datetime, datetime]] = []
        chunk_start = range_start
        while chunk_start < range_end:
            chunk_end = min(chunk_start + timedelta(minutes=historic_chunk_minutes), range_end)
            windows.append((chunk_start, chunk_end))
            chunk_start = chunk_end
        log.info("[%s] Historic mode: %s → %s (%d chunk(s) of %d min)",
                 source, range_start, range_end, len(windows), historic_chunk_minutes)
    else:
        now = datetime.now(timezone.utc)
        query_end = now.replace(second=0, microsecond=0) - timedelta(minutes=query_offset_minutes)
        query_start = query_end - timedelta(minutes=lookback)
        windows = [(query_start, query_end)]

    monitors: list[dict] = cfg.get("monitors") or []
    if not monitors:
        log.warning("[%s] No monitors defined — skipping", source)
        return

    if not check_and_create_project(
        user_name=if_user,
        license_key=if_key,
        project_name=if_project,
        system_name=if_system,
        sampling_interval=sampling_interval,
        if_url=if_url,
    ):
        log.error("[%s] Project not ready — skipping data send", source)
        return

    for window_start, window_end in windows:
        all_rows: list[dict] = []
        for monitor in monitors:
            try:
                rows = process_monitor(
                    monitor=monitor,
                    api_key=api_key, app_key=app_key, base_url=base_url,
                    start=window_start, end=window_end,
                    interval_seconds=interval_seconds,
                    rolling_window_seconds=rolling_window_seconds,
                    group_limit=group_limit,
                    default_component=default_component,
                )
                all_rows.extend(rows)
            except Exception:
                log.exception("[%s] Error processing monitor %r", source, monitor.get("name"))

        if not all_rows:
            log.info("[%s] No data to send for window %s→%s", source, window_start, window_end)
            continue

        for offset in range(0, len(all_rows), IF_BATCH_SIZE):
            batch = all_rows[offset:offset + IF_BATCH_SIZE]
            try:
                resp = send_metric_data_to_if(
                    user_name=if_user, license_key=if_key,
                    project_name=if_project, system_name=if_system,
                    metric_rows=batch, if_url=if_url,
                )
                log.info("[%s] Sent %d row(s) | %s", source, len(batch), resp)
            except requests.HTTPError as exc:
                log.error("[%s] InsightFinder HTTP %d: %s", source, exc.response.status_code, exc.response.text)
            except requests.ConnectionError as exc:
                log.error("[%s] InsightFinder network error: %s", source, exc)


CONF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conf.d")


def main() -> None:
    configs = load_configs(CONF_DIR)
    if not configs:
        log.error("No configs loaded from %s — exiting", CONF_DIR)
        sys.exit(1)
    for cfg in configs:
        try:
            process_config(cfg)
        except Exception:
            log.exception("Unhandled error processing %s", cfg.get("_source"))


if __name__ == "__main__":
    main()
