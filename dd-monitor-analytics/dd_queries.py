#!/usr/bin/env python3
"""
Parse and execute the two Datadog monitor query flavours we care about:

  - "query alert"           e.g.  sum(last_5m):sum:trace.servlet.request.hits{...} by {x}.as_count() > 15
                            executed via /api/v1/query  (metric timeseries)

  - "trace-analytics alert" e.g.  trace-analytics("FILTER").index("a","b").rollup("count").by("x,y").last("5m") > 10
                            executed via /api/v2/spans/analytics/aggregate  (span timeseries)

Both return the same shape:
    { group_key: [(epoch_ms, value), ...] }
where group_key is "_combined" when the query is not grouped, or the comma-joined
group-by values otherwise.
"""

import logging
import random
import re
import time
from datetime import datetime, timedelta
from typing import Any

import requests

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_GROUP_LIMIT = 20  # per-facet cap (combined cardinality × time buckets must stay ≤ 400k)

# Retry config for DD HTTP calls. DD's free-tier rate limits (300/h spans,
# 200/h metrics) make 429s common in practice; 5xx and connection errors are
# rarer but also transient. We back off exponentially and honour the
# `Retry-After` header DD sends with 429s.
DEFAULT_MAX_RETRIES = 5
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_BACKOFF_SECONDS = 60.0


def _request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    json: dict | None = None,
    timeout: int = 30,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> requests.Response | None:
    """
    Issue a DD HTTP request with retry on 429 / 5xx / network errors.

    On 429 responses we respect the `Retry-After` header when present;
    otherwise we use exponential backoff with jitter (2^attempt + random).
    Returns the final Response (which may still be an error if retries are
    exhausted) or None if a network error persists after all retries.
    """
    for attempt in range(max_retries + 1):
        try:
            resp = requests.request(
                method, url,
                headers=headers, params=params, json=json,
                timeout=timeout,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt >= max_retries:
                log.error("DD %s %s network error after %d retries: %s",
                          method, url, attempt, exc)
                return None
            wait = min(MAX_BACKOFF_SECONDS, 2 ** attempt + random.uniform(0, 1))
            log.warning("DD %s network error (%s), retry %d/%d in %.1fs",
                        method, exc.__class__.__name__, attempt + 1, max_retries, wait)
            time.sleep(wait)
            continue

        if resp.status_code in RETRY_STATUS_CODES and attempt < max_retries:
            # 429 → prefer Retry-After when DD provides it
            retry_after = resp.headers.get("Retry-After")
            try:
                wait = float(retry_after) if retry_after else 2 ** attempt + random.uniform(0, 1)
            except ValueError:
                wait = 2 ** attempt + random.uniform(0, 1)
            wait = min(MAX_BACKOFF_SECONDS, wait)
            log.warning("DD %s → HTTP %d%s, retry %d/%d in %.1fs",
                        method, resp.status_code,
                        f" (Retry-After: {retry_after})" if retry_after else "",
                        attempt + 1, max_retries, wait)
            time.sleep(wait)
            continue

        return resp

    return resp  # exhausted retries — caller will see the last non-2xx response


# ---------------------------------------------------------------------------
# query-alert (metric query)
# ---------------------------------------------------------------------------

_EVAL_AGG_PREFIX_RE = re.compile(r"^\s*\w+\s*\(\s*last_[^)]+\)\s*:\s*")
_THRESHOLD_SUFFIX_RE = re.compile(r"\s*(>=|<=|>|<|==|!=)\s*[-+\d.eE]+\s*$")
_HAS_ROLLUP_RE = re.compile(r"\.rollup\s*\(")
_LEADING_SPACE_AGG_RE = re.compile(r"^\s*(\w+)\s*:")
_VALID_ROLLUP_AGGS = {"sum", "avg", "min", "max", "count"}


def strip_metric_query(monitor_query: str) -> str:
    """
    Strip the evaluation aggregator prefix (e.g. 'sum(last_5m):') and the
    threshold comparison suffix (e.g. '> 15') from a query-alert query,
    leaving just the metric expression that /api/v1/query understands.
    """
    q = _EVAL_AGG_PREFIX_RE.sub("", monitor_query)
    q = _THRESHOLD_SUFFIX_RE.sub("", q)
    return q.strip()


def ensure_rollup(metric_query: str, interval_seconds: int) -> str:
    """
    Pin the response cadence by appending `.rollup(<agg>, <interval_seconds>)`
    when the query doesn't already specify one.

    Without an explicit rollup, /api/v1/query picks bucket width based on the
    time-window length (1h→60s, 1d→5m, 1w→1h, …). That breaks our wall-clock
    rolling sum, which assumes buckets are spaced at `interval_seconds`.

    Aggregator picked = the query's leading space aggregator (e.g. `sum:foo{*}`
    → `sum`), defaulting to `sum`. `sum` is correct for `.as_count()` /
    `.as_rate()` queries (counts and rates roll up by summation).
    """
    if _HAS_ROLLUP_RE.search(metric_query):
        return metric_query
    m = _LEADING_SPACE_AGG_RE.match(metric_query)
    if not m or m.group(1) not in _VALID_ROLLUP_AGGS:
        # Arithmetic, wrapping function, or anything not of the shape
        # `<agg>:<metric>{…}…`. We can't safely append `.rollup(...)` because
        # it'd attach to the wrong sub-expression. Leave the query alone and
        # warn — user must add per-metric `.rollup(...)`s explicitly.
        log.warning(
            "Cannot auto-pin cadence on this query (not a simple <agg>:metric{…} form). "
            "DD will choose bucket width by time-window length, which may not match "
            "interval_seconds=%ss. Add explicit .rollup(...) modifiers in the query. "
            "Query: %s", interval_seconds, metric_query,
        )
        return metric_query
    return f"{metric_query}.rollup({m.group(1)}, {interval_seconds})"


def execute_metric_query(
    *,
    api_key: str,
    app_key: str,
    base_url: str,
    metric_query: str,
    start: datetime,
    end: datetime,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> dict[str, list[tuple[int, float]]]:
    metric_query = ensure_rollup(metric_query, interval_seconds)
    log.debug("DD /api/v1/query: %s", metric_query)
    resp = _request_with_retry(
        "GET",
        f"{base_url.rstrip('/')}/api/v1/query",
        params={
            "from": int(start.timestamp()),
            "to": int(end.timestamp()),
            "query": metric_query,
        },
        headers={
            "DD-API-KEY": api_key,
            "DD-APPLICATION-KEY": app_key,
            "Accept": "application/json",
        },
    )
    if resp is None:
        return {}
    if not resp.ok:
        log.error("Datadog /api/v1/query HTTP %d: %s", resp.status_code, resp.text[:500])
        return {}

    out: dict[str, list[tuple[int, float]]] = {}
    for s in resp.json().get("series", []):
        scope = s.get("scope", "") or "_combined"
        pts = [
            (int(p[0]), float(p[1]))
            for p in s.get("pointlist", [])
            if len(p) == 2 and p[1] is not None
        ]
        if pts:
            out[scope] = sorted(pts)
    return out


# ---------------------------------------------------------------------------
# trace-analytics query
# ---------------------------------------------------------------------------

_TA_RE = re.compile(
    r'trace-analytics\(\s*"((?:[^"\\]|\\.)*)"\s*\)'  # 1: filter (handles escaped quotes)
    r'(.*?)'                                          # 2: chained modifiers
    r'\s*(?:(?:>=|<=|>|<|==|!=)\s*[-+\d.eE]+)?\s*$',  # optional threshold
    re.DOTALL,
)
_TA_INDEX_RE = re.compile(r'\.index\(([^)]*)\)')
_TA_ROLLUP_RE = re.compile(r'\.rollup\(\s*"([^"]+)"(?:\s*,\s*"?([^"\)]+)"?)?\s*\)')
_TA_BY_RE = re.compile(r'\.by\(\s*"([^"]+)"\s*\)')
_TA_LAST_RE = re.compile(r'\.last\(\s*"([^"]+)"\s*\)')


def parse_trace_analytics_query(monitor_query: str) -> dict[str, Any] | None:
    """Parse the chained trace-analytics() DSL into components."""
    m = _TA_RE.search(monitor_query)
    if not m:
        return None
    raw_filter = m.group(1).replace('\\"', '"')
    chain = m.group(2) or ""

    indexes: list[str] = []
    if (im := _TA_INDEX_RE.search(chain)):
        indexes = [s.strip().strip('"').strip("'") for s in im.group(1).split(",") if s.strip()]

    aggregator = "count"
    rollup_metric: str | None = None
    if (rm := _TA_ROLLUP_RE.search(chain)):
        aggregator = rm.group(1)
        rollup_metric = rm.group(2)

    group_by: list[str] = []
    if (bm := _TA_BY_RE.search(chain)):
        group_by = [s.strip() for s in bm.group(1).split(",") if s.strip()]

    last = "5m"
    if (lm := _TA_LAST_RE.search(chain)):
        last = lm.group(1)

    return {
        "filter": raw_filter,
        "indexes": indexes,
        "aggregator": aggregator,
        "rollup_metric": rollup_metric,
        "group_by": group_by,
        "last": last,
    }


def execute_trace_analytics_query(
    *,
    api_key: str,
    app_key: str,
    base_url: str,
    parsed: dict[str, Any],
    start: datetime,
    end: datetime,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    group_limit: int = DEFAULT_GROUP_LIMIT,
) -> dict[str, list[tuple[int, float]]]:
    """
    Execute a parsed trace-analytics query against /api/v2/spans/analytics/aggregate.

    Returns a per-group timeseries: {group_key: [(epoch_ms, value), ...]}.
    """
    aggregator = parsed.get("aggregator") or "count"
    compute_entry: dict[str, Any] = {
        "aggregation": aggregator,
        "type": "timeseries",
        "interval": f"{interval_seconds}s",
    }
    if parsed.get("rollup_metric") and aggregator != "count":
        compute_entry["metric"] = parsed["rollup_metric"]

    body: dict[str, Any] = {
        "data": {
            "type": "aggregate_request",
            "attributes": {
                "compute": [compute_entry],
                "filter": {
                    "from": start.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    "to": end.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    "query": parsed.get("filter") or "*",
                },
                "options": {"timezone": "UTC"},
            },
        }
    }
    if parsed.get("group_by"):
        body["data"]["attributes"]["group_by"] = [
            {"facet": f, "limit": group_limit, "total": False}
            for f in parsed["group_by"]
        ]

    log.debug("DD spans-aggregate request body: %s", body)
    resp = _request_with_retry(
        "POST",
        f"{base_url.rstrip('/')}/api/v2/spans/analytics/aggregate",
        json=body,
        headers={
            "DD-API-KEY": api_key,
            "DD-APPLICATION-KEY": app_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    if resp is None:
        return {}
    if not resp.ok:
        log.error("Datadog spans aggregate HTTP %d: %s", resp.status_code, resp.text[:500])
        return {}

    payload = resp.json() or {}
    raw = payload.get("data") or []
    if not raw:
        import json as _json
        log.warning("DD spans-aggregate empty response:\n%s",
                    _json.dumps(payload, indent=2)[:2000])
    # /api/v2/spans/analytics/aggregate returns either a JSON:API-style list of
    # bucket resources ({"data": [{"attributes": {"by":…, "computes":…}}, …]})
    # or, less commonly, an object with a "buckets" list. Handle both.
    if isinstance(raw, dict):
        buckets = raw.get("buckets") or []
    else:
        buckets = raw

    out: dict[str, list[tuple[int, float]]] = {}
    for b in buckets:
        attrs = b.get("attributes") if isinstance(b, dict) and "attributes" in b else b
        by = (attrs or {}).get("by") or {}
        if parsed.get("group_by"):
            key = ",".join(str(by.get(f, "")) for f in parsed["group_by"]) or "_unknown"
        else:
            key = "_combined"

        # DD returns the field as "compute" (singular); accept both spellings.
        computes = (attrs or {}).get("compute") or (attrs or {}).get("computes") or {}
        # Single compute → values keyed e.g. "c0" or by aggregator name; just take the first.
        if not computes:
            continue
        first_compute = next(iter(computes.values()))
        # Timeseries computes look like: [{"time": "...", "value": N}, ...]
        if not isinstance(first_compute, list):
            continue

        pts: list[tuple[int, float]] = []
        for entry in first_compute:
            if not isinstance(entry, dict):
                continue
            t = entry.get("time")
            v = entry.get("value")
            if t is None or v is None:
                continue
            try:
                ts_ms = int(datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() * 1000)
            except Exception:
                continue
            try:
                pts.append((ts_ms, float(v)))
            except (TypeError, ValueError):
                continue
        if pts:
            out[key] = sorted(pts)
    return out


# ---------------------------------------------------------------------------
# rolling aggregation (to mirror DD's monitor evaluation, e.g. ".last(5m)")
# ---------------------------------------------------------------------------


def apply_rolling_sum(
    series: dict[str, list[tuple[int, float]]],
    *,
    window_seconds: int,
    interval_seconds: int,
    emit_start_ms: int,
    emit_end_ms: int,
) -> dict[str, list[tuple[int, float]]]:
    """
    Wall-clock-based rolling sum. For every minute T in
        [emit_start_ms, emit_end_ms)  (step = interval_seconds)
    emit a point whose value is the sum of all returned bucket counts whose
    timestamp falls in (T - window_seconds, T].

    Datadog's spans-aggregate API omits zero-count buckets, so we cannot rely
    on the returned list being contiguous — index-based sliding produces both
    data gaps (no points emitted for quiet minutes) and incorrect sums (the
    "last 5 entries" can span hours when traffic is sparse). Densifying to a
    dict keyed by epoch_ms and iterating wall-clock minutes fixes both.

    This mirrors how a Datadog monitor with `.rollup("count").last("Xm")`
    plots its evaluated value: a refreshing X-minute count at every tick.
    """
    interval_ms = interval_seconds * 1000
    window_ms = window_seconds * 1000

    # Align emit timestamps to the interval grid relative to emit_start_ms.
    out: dict[str, list[tuple[int, float]]] = {}
    for key, pts in series.items():
        if not pts:
            continue
        bucket_map = {ts: val for ts, val in pts}
        # The set of bucket timestamps within the rolling window of T is
        # {T - interval, T - 2*interval, …, T - window + interval, T}.
        # Iterate T over the emit grid and accumulate via a sliding window.
        # For O(N) we use a running sum, adding the new bucket entering on the
        # right and dropping the one leaving on the left.
        rolled: list[tuple[int, float]] = []
        running = 0.0
        # Pre-seed: add buckets in (emit_start_ms - window, emit_start_ms].
        seed_lower = emit_start_ms - window_ms
        t = seed_lower + interval_ms
        while t <= emit_start_ms:
            running += bucket_map.get(t, 0.0)
            t += interval_ms

        T = emit_start_ms
        while T < emit_end_ms:
            rolled.append((T, running))
            # Slide window forward by one interval.
            T_next = T + interval_ms
            running += bucket_map.get(T_next, 0.0)              # new right-edge bucket
            running -= bucket_map.get(T_next - window_ms, 0.0)  # bucket falling off left
            T = T_next
        out[key] = rolled
    return out


# ---------------------------------------------------------------------------
# unified entry point
# ---------------------------------------------------------------------------


def execute_monitor_query(
    *,
    monitor_type: str,
    monitor_query: str | None = None,
    parsed_query: dict[str, Any] | None = None,
    api_key: str,
    app_key: str,
    base_url: str,
    start: datetime,
    end: datetime,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    rolling_window_seconds: int | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
) -> dict[str, list[tuple[int, float]]]:
    """
    `rolling_window_seconds` — if set and larger than `interval_seconds`, the
    returned per-bucket counts are converted to a rolling sum of that window
    width, emitted at `interval_seconds` cadence. Use this to match a DD
    monitor's `.last("Xm")` evaluation exactly (e.g. 300 → rolling 5-minute
    count, refreshed every minute).
    """
    use_rolling = bool(rolling_window_seconds and rolling_window_seconds > interval_seconds)
    if use_rolling:
        # Fetch with pre-roll so the very first emit minute has a full window of
        # history available to sum.
        fetch_start = start - timedelta(seconds=rolling_window_seconds - interval_seconds)
    else:
        fetch_start = start

    mt = (monitor_type or "").lower()
    if "trace-analytics" in mt:
        parsed = parsed_query or (parse_trace_analytics_query(monitor_query) if monitor_query else None)
        if not parsed:
            log.error("trace-analytics: neither parsed_query nor parseable monitor_query provided")
            return {}
        log.info("trace-analytics: filter=%r group_by=%s agg=%s rolling=%ss interval=%ss",
                 parsed.get("filter"), parsed.get("group_by"), parsed.get("aggregator"),
                 rolling_window_seconds, interval_seconds)
        series = execute_trace_analytics_query(
            api_key=api_key, app_key=app_key, base_url=base_url,
            parsed=parsed, start=fetch_start, end=end,
            interval_seconds=interval_seconds,
            group_limit=group_limit,
        )
    else:
        if not monitor_query:
            log.error("query alert: monitor_query is required")
            return {}
        metric_query = strip_metric_query(monitor_query)
        log.info("metric query: %s (rolling=%ss interval=%ss)",
                 metric_query, rolling_window_seconds, interval_seconds)
        series = execute_metric_query(
            api_key=api_key, app_key=app_key, base_url=base_url,
            metric_query=metric_query, start=fetch_start, end=end,
            interval_seconds=interval_seconds,
        )

    if use_rolling:
        series = apply_rolling_sum(
            series,
            window_seconds=rolling_window_seconds,
            interval_seconds=interval_seconds,
            emit_start_ms=int(start.timestamp() * 1000),
            emit_end_ms=int(end.timestamp() * 1000),
        )
    return series
