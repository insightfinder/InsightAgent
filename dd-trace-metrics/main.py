#!/usr/bin/env python3
"""
Datadog HTTP Availability Metrics → InsightFinder

Queries Datadog APM for HTTP availability metrics (total requests, 500 errors,
availability %) and streams them to an InsightFinder metric project.

Designed to be triggered repeatedly by a cron job, e.g.:
    */5 * * * * /path/to/venv/bin/python /path/to/main.py
"""

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

from insightfinder import check_and_create_project, send_metric_data_to_if

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("dd-http-availability")

DEFAULT_DD_ENDPOINT = "https://api.datadoghq.eu"
DEFAULT_LOOKBACK_MINUTES = 5
DEFAULT_SAMPLING_INTERVAL = 60
IF_BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Query builder — the only place queries are defined
# ---------------------------------------------------------------------------


def build_queries(
    framework: str,
    tags: dict[str, str],
    split_by: str | None = None,
) -> tuple[str, str]:
    """
    Build total-requests and 500-errors Datadog metric queries.

    - tags      : filter tags slotted into the query scope
    - split_by  : if set, appends `by {tag}` so Datadog returns one series
                  per value of that tag (used for auto instance discovery)

    All queries use a fixed 60-second rollup so every data point is always a
    per-minute count, regardless of query window width.
    """
    tag_parts = [f"{k}:{v}" for k, v in tags.items() if v]
    tag_filter = ",".join(tag_parts) if tag_parts else "*"
    by_clause = f" by {{{split_by}}}" if split_by else ""
    total_query     = f"sum:trace.{framework}.request.hits{{{tag_filter}}}{by_clause}.as_count().rollup(sum, 60)"
    error_500_query = f"sum:trace.{framework}.request.errors{{{tag_filter},http.status_code:500}}{by_clause}.as_count().rollup(sum, 60)"
    error_5xx_query = f"sum:trace.{framework}.request.errors{{{tag_filter}}}{by_clause}.as_count().rollup(sum, 60)"
    return total_query, error_500_query, error_5xx_query


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Datadog timeseries query
# ---------------------------------------------------------------------------


def _dd_query(
    *,
    api_key: str,
    app_key: str,
    query: str,
    start: datetime,
    end: datetime,
    base_url: str,
) -> list[dict]:
    """Return the raw series list from Datadog /api/v1/query."""
    try:
        resp = requests.get(
            f"{base_url.rstrip('/')}/api/v1/query",
            params={
                "from": int(start.timestamp()),
                "to": int(end.timestamp()),
                "query": query,
            },
            headers={
                "DD-API-KEY": api_key,
                "DD-APPLICATION-KEY": app_key,
                "Accept": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
    except requests.HTTPError as exc:
        log.error("Datadog API HTTP %d: %s", exc.response.status_code, exc.response.text)
        return []
    except requests.ConnectionError as exc:
        log.error("Datadog API network error: %s", exc)
        return []

    return resp.json().get("series", [])


def _extract_tag_value(scope: str, tag: str) -> str:
    """Pull a tag value out of a Datadog scope string like 'env:prod,service:foo'."""
    for part in scope.split(","):
        part = part.strip()
        if part.startswith(f"{tag}:"):
            return part[len(tag) + 1:]
    return scope  # fall back to full scope if tag not found


def _series_to_points(series: list[dict]) -> dict[str, dict[int, float]]:
    """
    Convert a list of Datadog series into:
        { scope_string: { epoch_ms: value } }
    """
    result: dict[str, dict[int, float]] = {}
    for s in series:
        scope = s.get("scope", "")
        pts: dict[int, float] = {}
        for point in s.get("pointlist", []):
            if len(point) == 2 and point[1] is not None:
                pts[int(point[0])] = float(point[1])
        if pts:
            result[scope] = pts
    return result


def query_timeseries(
    *,
    api_key: str,
    app_key: str,
    frameworks: list[str],
    tags: dict[str, str],
    split_by: str | None,
    start: datetime,
    end: datetime,
    base_url: str,
) -> dict[str, tuple[list[tuple[int, float]], list[tuple[int, float]]]]:
    """
    Query total-requests and 500-errors across all frameworks and return
    per-instance timeseries.

    When split_by is set:
        Datadog returns one series per tag value → each becomes its own
        instance keyed by that tag value (e.g. "checkout-service").

    When split_by is None:
        All series are merged into a single instance keyed by "_combined".

    Returns:
        { instance_name: (total_points, error_points) }
    where points are sorted lists of (epoch_ms, value).
    """
    # Accumulate across frameworks: instance → { ts: total/error }
    total_by_instance: dict[str, dict[int, float]] = {}
    error_500_by_instance: dict[str, dict[int, float]] = {}
    error_5xx_by_instance: dict[str, dict[int, float]] = {}

    for framework in frameworks:
        total_query, error_500_query, error_5xx_query = build_queries(framework, tags, split_by)
        log.debug("total query  : %s", total_query)
        log.debug("500 query    : %s", error_500_query)
        log.debug("5xx query    : %s", error_5xx_query)

        for scope, pts in _series_to_points(_dd_query(
            api_key=api_key, app_key=app_key, query=total_query,
            start=start, end=end, base_url=base_url,
        )).items():
            key = _extract_tag_value(scope, split_by) if split_by else "_combined"
            bucket = total_by_instance.setdefault(key, {})
            log.info("  [debug] framework=%s  instance=%s  points=%d  sum=%.0f", framework, key, len(pts), sum(pts.values()))
            for ts, val in pts.items():
                bucket[ts] = bucket.get(ts, 0.0) + val

        for scope, pts in _series_to_points(_dd_query(
            api_key=api_key, app_key=app_key, query=error_500_query,
            start=start, end=end, base_url=base_url,
        )).items():
            key = _extract_tag_value(scope, split_by) if split_by else "_combined"
            bucket = error_500_by_instance.setdefault(key, {})
            for ts, val in pts.items():
                bucket[ts] = bucket.get(ts, 0.0) + val

        for scope, pts in _series_to_points(_dd_query(
            api_key=api_key, app_key=app_key, query=error_5xx_query,
            start=start, end=end, base_url=base_url,
        )).items():
            key = _extract_tag_value(scope, split_by) if split_by else "_combined"
            bucket = error_5xx_by_instance.setdefault(key, {})
            for ts, val in pts.items():
                bucket[ts] = bucket.get(ts, 0.0) + val

    return {
        inst: (
            sorted(total_by_instance[inst].items()),
            sorted(error_500_by_instance.get(inst, {}).items()),
            sorted(error_5xx_by_instance.get(inst, {}).items()),
        )
        for inst in total_by_instance
    }


# ---------------------------------------------------------------------------
# Metric row builder
# ---------------------------------------------------------------------------


def build_metric_rows(
    *,
    total_points: list[tuple[int, float]],
    error_500_points: list[tuple[int, float]],
    error_5xx_points: list[tuple[int, float]],
    instance_name: str,
    component_name: str,
) -> list[dict]:
    error_500_map = dict(error_500_points)
    error_5xx_map = dict(error_5xx_points)
    rows = []
    for ts_ms, total in total_points:
        errors_500 = error_500_map.get(ts_ms, 0.0)
        errors_5xx = error_5xx_map.get(ts_ms, 0.0)
        availability = ((total - errors_5xx) / total * 100.0) if total > 0 else 100.0
        rows.append({
            "instanceName": instance_name,
            "componentName": component_name,
            "timestamp": ts_ms,
            "total_requests": total,
            "http_500_requests": errors_500,
            "availability_pct": round(availability, 4),
        })
    return rows


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

    raw_fw = dd.get("frameworks") or dd.get("framework") or ["servlet"]
    default_frameworks: list[str] = [raw_fw] if isinstance(raw_fw, str) else list(raw_fw)

    if not api_key or not app_key:
        log.error("[%s] Missing Datadog api_key or application_key — skipping", source)
        return

    # ── InsightFinder credentials ────────────────────────────────────────────
    if_url: str = if_cfg.get("url") or ""
    if_user: str = if_cfg.get("username") or ""
    if_key: str = if_cfg.get("license_key") or ""
    if_project: str = if_cfg.get("project") or ""
    if_system: str = if_cfg.get("system_name") or if_project

    if not all([if_url, if_user, if_key, if_project]):
        log.error("[%s] Incomplete InsightFinder config — skipping", source)
        return

    # ── Time window ──────────────────────────────────────────────────────────
    lookback: int = int(agent_cfg.get("lookback") or DEFAULT_LOOKBACK_MINUTES)
    sampling_interval: int = int(agent_cfg.get("sampling_interval") or DEFAULT_SAMPLING_INTERVAL)

    historic_range: str = agent_cfg.get("historic_time_range") or ""
    historic_chunk_minutes: int = int(agent_cfg.get("historic_chunk_minutes") or 60)
    query_offset_minutes: int = int(agent_cfg.get("query_offset_minutes") or 0)

    if historic_range:
        try:
            start_str, end_str = [s.strip() for s in historic_range.split(",", 1)]
            range_start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            range_end   = datetime.strptime(end_str,   "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            log.error("[%s] Invalid historic_time_range format (expected 'YYYY-MM-DD HH:MM:SS,YYYY-MM-DD HH:MM:SS'): %r", source, historic_range)
            return
        windows: list[tuple[datetime, datetime]] = []
        chunk_start = range_start
        while chunk_start < range_end:
            chunk_end = min(chunk_start + timedelta(minutes=historic_chunk_minutes), range_end)
            windows.append((chunk_start, chunk_end))
            chunk_start = chunk_end
        log.info("[%s] Historic mode: %s → %s  (%d chunk(s) of %d min)", source, range_start, range_end, len(windows), historic_chunk_minutes)
    else:
        now = datetime.now(timezone.utc)
        query_end   = now.replace(second=0, microsecond=0) - timedelta(minutes=query_offset_minutes)
        query_start = query_end - timedelta(minutes=lookback)
        windows = [(query_start, query_end)]

    # ── Ensure project exists ────────────────────────────────────────────────
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

    # ── Instances ────────────────────────────────────────────────────────────
    instances: list[dict] = dd.get("services") or []
    if not instances:
        log.warning("[%s] No services defined — skipping", source)
        return

    for window_start, window_end in windows:
        all_rows: list[dict] = []

        for inst in instances:
            tags: dict[str, str] = inst.get("tags") or {}
            component_name: str = inst.get("component_name") or ""
            component_name_from_tag: str | None = inst.get("component_name_from_tag") or None

            raw_inst_fw = inst.get("frameworks") or inst.get("framework")
            inst_frameworks = (
                [raw_inst_fw] if isinstance(raw_inst_fw, str)
                else list(raw_inst_fw) if raw_inst_fw
                else default_frameworks
            )

            instance_name: str | None = inst.get("instance_name") or None
            instance_name_from_tag: str | None = inst.get("instance_name_from_tag") or None

            if not instance_name and not instance_name_from_tag:
                log.warning("[%s] service entry must have 'instance_name' or 'instance_name_from_tag' — skipping", source)
                continue

            # instance_name_from_tag: split by that tag, each unique value becomes an instance
            # instance_name:          fixed string, all matching series merged into one instance
            if instance_name_from_tag:
                split_by, fixed_name = instance_name_from_tag, None
            else:
                split_by, fixed_name = None, instance_name

            log.info(
                "[%s] querying  frameworks=%s  tags=%s  split_by=%s  window=%s→%s",
                source, inst_frameworks, tags, split_by or "(combined)", window_start, window_end,
            )

            results = query_timeseries(
                api_key=api_key, app_key=app_key,
                frameworks=inst_frameworks, tags=tags,
                split_by=split_by,
                start=window_start, end=window_end, base_url=base_url,
            )

            for discovered_name, (total_points, error_500_points, error_5xx_points) in results.items():
                instance_name = fixed_name or discovered_name
                resolved_component = (
                    _extract_tag_value(discovered_name, component_name_from_tag)
                    if component_name_from_tag else component_name
                )
                log.info(
                    "[%s] instance=%r  component=%r  total=%d  500s=%d  5xx=%d",
                    source, instance_name, resolved_component or "(none)",
                    len(total_points), len(error_500_points), len(error_5xx_points),
                )
                all_rows.extend(build_metric_rows(
                    total_points=total_points,
                    error_500_points=error_500_points,
                    error_5xx_points=error_5xx_points,
                    instance_name=instance_name,
                    component_name=resolved_component,
                ))

        if not all_rows:
            log.info("[%s] No metric data to send for window %s→%s", source, window_start, window_end)
            continue

        # ── Send to InsightFinder ────────────────────────────────────────────────
        for offset in range(0, len(all_rows), IF_BATCH_SIZE):
            batch = all_rows[offset: offset + IF_BATCH_SIZE]
            try:
                resp = send_metric_data_to_if(
                    user_name=if_user, license_key=if_key,
                    project_name=if_project, system_name=if_system,
                    metric_rows=batch, if_url=if_url,
                )
                log.info("[%s] Sent %d row(s) to InsightFinder | %s", source, len(batch), resp)
            except requests.HTTPError as exc:
                log.error("[%s] InsightFinder HTTP %d: %s", source, exc.response.status_code, exc.response.text)
            except requests.ConnectionError as exc:
                log.error("[%s] InsightFinder network error: %s", source, exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

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
