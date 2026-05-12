#!/usr/bin/env python3
"""
Datadog metric discovery script.

Fill in DD_API_KEY, DD_APP_KEY, and DD_ENDPOINT at the top of this file,
then run:

    python discover.py

CLI flags override the in-script values if supplied:

    python discover.py --api-key xxx --app-key yyy --endpoint https://api.datadoghq.eu

Output is printed to stdout so you can pipe it:

    python discover.py | tee discovery_results.txt
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Configuration — fill these in before running
# ---------------------------------------------------------------------------

DD_API_KEY = ""
DD_APP_KEY = ""
DD_ENDPOINT = "https://api.datadoghq.eu"

# ---------------------------------------------------------------------------

LOOKBACK_HOURS = 4  # how far back to look for recent data


# ---------------------------------------------------------------------------
# Datadog API helpers
# ---------------------------------------------------------------------------


def dd_get(
    path: str,
    *,
    api_key: str,
    app_key: str,
    base_url: str,
    params: dict | None = None,
) -> Any:
    headers = {
        "DD-API-KEY": api_key,
        "DD-APPLICATION-KEY": app_key,
        "Accept": "application/json",
    }
    url = f"{base_url.rstrip('/')}{path}"
    resp = requests.get(url, headers=headers, params=params or {}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def dd_post(
    path: str,
    *,
    api_key: str,
    app_key: str,
    base_url: str,
    body: dict,
) -> Any:
    headers = {
        "DD-API-KEY": api_key,
        "DD-APPLICATION-KEY": app_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    url = f"{base_url.rstrip('/')}{path}"
    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def ok(msg: str) -> None:
    print(f"  [OK]  {msg}")


def warn(msg: str) -> None:
    print(f"  [!!]  {msg}")


def info(msg: str) -> None:
    print(f"        {msg}")


# ---------------------------------------------------------------------------
# Step 1 – validate credentials
# ---------------------------------------------------------------------------


def check_credentials(api_key: str, app_key: str, base_url: str) -> bool:
    section("1. Credential validation")
    try:
        resp = dd_get("/api/v1/validate", api_key=api_key, app_key=app_key, base_url=base_url)
        if resp.get("valid"):
            ok("API key is valid")
        else:
            warn(f"API key validation response: {resp}")
            return False
    except requests.HTTPError as exc:
        warn(f"API key check failed: {exc.response.status_code} {exc.response.text}")
        return False
    except requests.ConnectionError as exc:
        warn(f"Cannot reach {base_url}: {exc}")
        return False

    # App key check — list dashboards (lightweight call that requires app key)
    try:
        dd_get("/api/v1/dashboard", api_key=api_key, app_key=app_key, base_url=base_url,
               params={"count": 1})
        ok("Application key is valid")
    except requests.HTTPError as exc:
        warn(f"Application key check failed ({exc.response.status_code}) — metrics queries may still work")

    return True


# ---------------------------------------------------------------------------
# Step 2 – search for trace.* metrics
# ---------------------------------------------------------------------------


def find_trace_metrics(api_key: str, app_key: str, base_url: str) -> list[str]:
    section("2. Searching for trace.* APM metrics")

    now_s = int(datetime.now(timezone.utc).timestamp())
    window_start = now_s - LOOKBACK_HOURS * 3600

    try:
        resp = dd_get(
            "/api/v1/metrics",
            api_key=api_key,
            app_key=app_key,
            base_url=base_url,
            params={"q": "trace.", "from": window_start},
        )
    except requests.HTTPError as exc:
        warn(f"Metric search failed: {exc.response.status_code} {exc.response.text}")
        return []

    all_metrics: list[str] = resp.get("metrics", [])
    if not all_metrics:
        warn("No trace.* metrics found in the past 4 hours.")
        info("This could mean: APM is not instrumented, or the lookback window is too short.")
        return []

    ok(f"Found {len(all_metrics)} trace.* metric(s) total")

    # Focus on top-level HTTP request spans — these are the framework-level
    # metrics that represent total HTTP traffic (not per-controller spans).
    HTTP_PATTERNS = (
        ".request.hits", ".request.errors",
        ".request.duration",
    )
    http_metrics = [m for m in all_metrics if any(m.endswith(p) for p in HTTP_PATTERNS)]

    if http_metrics:
        info(f"-- Top-level HTTP request metrics ({len(http_metrics)} found):")
        for m in sorted(http_metrics):
            info(f"   {m}")
    else:
        # Fall back: show all hits/errors metrics
        info("No *.request.hits/errors found — showing all .hits/.errors metrics:")
        for m in sorted(m for m in all_metrics if m.endswith((".hits", ".errors"))):
            info(f"   {m}")

    return all_metrics


# ---------------------------------------------------------------------------
# Step 3 – targeted probe for HTTP frameworks we care about
# ---------------------------------------------------------------------------

# Frameworks most likely to represent HTTP server traffic in a TUI/travel
# backend.  We probe hits + errors for each, scoped to env:prod.
HTTP_FRAMEWORKS = [
    "aspnet_core",
    "aspnet",
    "servlet",
    "web",
    "express",
    "fastapi",
    "koa",
    "next",
    "symfony",
    "django",
    "flask",
    "requests",
]


def probe_http_frameworks(
    all_metrics: list[str], api_key: str, app_key: str, base_url: str
) -> dict[str, dict]:
    """
    For each HTTP framework, query hits and errors scoped to env:prod,
    broken out by service tag.  Also checks whether http.status_code:500
    is present on error metrics.

    Returns a dict keyed by framework name with findings.
    """
    section("3. Targeted HTTP framework probe (env:prod)")

    metric_set = set(all_metrics)
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=LOOKBACK_HOURS)
    time_params = {"from": int(start.timestamp()), "to": int(now.timestamp())}

    findings: dict[str, dict] = {}

    for fw in HTTP_FRAMEWORKS:
        hits_metric   = f"trace.{fw}.request.hits"
        errors_metric = f"trace.{fw}.request.errors"

        hits_exists   = hits_metric in metric_set
        errors_exists = errors_metric in metric_set

        if not hits_exists:
            continue  # framework not instrumented — skip silently

        info(f"")
        info(f"Framework: {fw}")
        info(f"  hits metric  : {hits_metric}  ({'exists' if hits_exists else 'MISSING'})")
        info(f"  errors metric: {errors_metric}  ({'exists' if errors_exists else 'MISSING'})")

        fw_data: dict = {"hits_metric": hits_metric, "errors_metric": errors_metric if errors_exists else None, "services": [], "has_500_tag": False}

        # ── Hits: discover prod services ─────────────────────────────────
        try:
            resp = dd_get("/api/v1/query", api_key=api_key, app_key=app_key, base_url=base_url,
                          params={**time_params, "query": f"sum:{hits_metric}{{env:prod}} by {{service}}"})
            series = resp.get("series", [])
            services = sorted({s.get("scope", "") for s in series if s.get("scope")})
            fw_data["services"] = services
            total_pts = sum(len([p for p in s.get("pointlist", []) if p[1] is not None]) for s in series)
            if services:
                ok(f"  {len(services)} prod service(s), {total_pts} data points")
                for svc in services:
                    info(f"    {svc}")
            else:
                warn(f"  No prod data found for {hits_metric}")
        except requests.HTTPError as exc:
            warn(f"  hits query failed: {exc.response.status_code}")

        # ── Errors: check http.status_code:500 tag ───────────────────────
        if errors_exists:
            try:
                resp = dd_get("/api/v1/query", api_key=api_key, app_key=app_key, base_url=base_url,
                              params={**time_params, "query": f"sum:{errors_metric}{{env:prod}} by {{http.status_code}}"})
                series = resp.get("series", [])
                status_codes = sorted({s.get("scope", "") for s in series if s.get("scope")})
                has_500 = any("500" in sc for sc in status_codes)
                fw_data["has_500_tag"] = has_500
                if status_codes:
                    tag_status = "YES — http.status_code tag populated" if has_500 else "tag present but no 500s found"
                    ok(f"  Error tag check: {tag_status}")
                    for sc in status_codes:
                        info(f"    {sc}")
                else:
                    warn(f"  No error data in env:prod — cannot confirm http.status_code tag")
            except requests.HTTPError as exc:
                warn(f"  errors query failed: {exc.response.status_code}")

        findings[fw] = fw_data

    return findings


# ---------------------------------------------------------------------------
# Step 4 – generate recommended config snippets from targeted findings
# ---------------------------------------------------------------------------


def generate_targeted_recommendations(findings: dict[str, dict]) -> None:
    section("4. Recommended config.yaml snippets (env:prod only)")

    if not findings:
        warn("No frameworks with live prod data found.")
        return

    for fw, data in findings.items():
        hits_m   = data["hits_metric"]
        errors_m = data["errors_metric"]
        services = data["services"]
        has_500  = data["has_500_tag"]

        if not services:
            continue

        info(f"# Framework: {fw}")
        info( "services:")
        for svc_scope in services:
            # svc_scope looks like "service:booking-api"
            svc_name = svc_scope.replace("service:", "")
            info(f"  - instance_name: \"{svc_name}\"")
            info(f"    total_requests_query: \"sum:{hits_m}{{env:prod,service:{svc_name}}}.as_count()\"")
            if errors_m and has_500:
                info(f"    http_500_query: \"sum:{errors_m}{{env:prod,service:{svc_name},http.status_code:500}}.as_count()\"")
            elif errors_m:
                info(f"    http_500_query: \"sum:{errors_m}{{env:prod,service:{svc_name}}}.as_count()\"")
                info( "    # NOTE: http.status_code:500 tag not confirmed — query returns ALL errors")
            else:
                info( "    http_500_query: \"\"  # no errors metric found for this framework")
        print()


# ---------------------------------------------------------------------------
# Write frameworks to file
# ---------------------------------------------------------------------------


def write_frameworks_file(frameworks: list[str], path: str = "discovered_frameworks.yaml") -> None:
    lines = ["frameworks:\n"]
    for fw in frameworks:
        lines.append(f"  - {fw}\n")
    with open(path, "w") as fh:
        fh.writelines(lines)
    ok(f"Frameworks written to {path} ({len(frameworks)} total)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover Datadog APM trace metrics available in your account."
    )
    parser.add_argument("--api-key", default=DD_API_KEY, help="Datadog API key")
    parser.add_argument("--app-key", default=DD_APP_KEY, help="Datadog Application key")
    parser.add_argument("--endpoint", default=DD_ENDPOINT, help="Datadog API base URL")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also write raw findings to discovery_results.json",
    )
    args = parser.parse_args()

    if not args.api_key or not args.app_key:
        parser.error("DD_API_KEY and DD_APP_KEY must be set in the script or passed via --api-key / --app-key")

    print(f"\nDatadog HTTP Availability — metric discovery")
    print(f"Endpoint : {args.endpoint}")
    print(f"Lookback : {LOOKBACK_HOURS} hours")

    if not check_credentials(args.api_key, args.app_key, args.endpoint):
        sys.exit(1)

    all_metrics = find_trace_metrics(args.api_key, args.app_key, args.endpoint)
    if not all_metrics:
        sys.exit(0)

    # Extract framework names from trace.<framework>.request.hits metrics
    frameworks = sorted({
        m[len("trace."):m.rfind(".request.hits")]
        for m in all_metrics
        if m.startswith("trace.") and m.endswith(".request.hits")
    })
    write_frameworks_file(frameworks)

    findings = probe_http_frameworks(all_metrics, args.api_key, args.app_key, args.endpoint)
    generate_targeted_recommendations(findings)

    if args.json:
        with open("discovery_results.json", "w") as fh:
            json.dump(findings, fh, indent=2)
        print(f"\nRaw results written to discovery_results.json")

    section("Done")


if __name__ == "__main__":
    main()
