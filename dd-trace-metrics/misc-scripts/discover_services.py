#!/usr/bin/env python3
"""
Find which APM frameworks are active for a list of service names.

Usage:
    python discover_services.py hybris_/destinations hybris_retail
    python discover_services.py --hours 24 hybris_/fi hybris_/cruise
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

DD_API_KEY  = ""
DD_APP_KEY  = ""
DD_ENDPOINT = "https://api.datadoghq.eu"

LOOKBACK_HOURS = 4
FRAMEWORKS_FILE = "discovered_frameworks.yaml"


def dd_has_data(query, *, api_key, app_key, base_url, start, end) -> bool:
    try:
        resp = requests.get(
            f"{base_url.rstrip('/')}/api/v1/query",
            params={"from": int(start.timestamp()), "to": int(end.timestamp()), "query": query},
            headers={"DD-API-KEY": api_key, "DD-APPLICATION-KEY": app_key, "Accept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.HTTPError:
        return False
    except requests.ConnectionError:
        return False

    for s in resp.json().get("series", []):
        if any(len(p) == 2 and p[1] is not None for p in s.get("pointlist", [])):
            return True
    return False


def find_frameworks(service: str, frameworks: list[str], *, api_key, app_key, base_url, start, end) -> list[str]:
    active = []
    for fw in frameworks:
        query = f"sum:trace.{fw}.request.hits{{service:{service}}}.as_count()"
        if dd_has_data(query, api_key=api_key, app_key=app_key, base_url=base_url, start=start, end=end):
            active.append(fw)
    return active


def main():
    parser = argparse.ArgumentParser(description="Find active APM frameworks for given service names.")
    parser.add_argument("services", nargs="+", help="Datadog service tag values to probe")
    parser.add_argument("--hours", type=int, default=LOOKBACK_HOURS, help="Lookback window in hours (default: 4)")
    parser.add_argument("--api-key",  default=DD_API_KEY)
    parser.add_argument("--app-key",  default=DD_APP_KEY)
    parser.add_argument("--endpoint", default=DD_ENDPOINT)
    parser.add_argument("--frameworks-file", default=FRAMEWORKS_FILE)
    args = parser.parse_args()

    fw_path = Path(args.frameworks_file)
    if not fw_path.exists():
        print(f"Frameworks file not found: {fw_path}")
        sys.exit(1)
    with open(fw_path) as fh:
        frameworks: list[str] = yaml.safe_load(fh).get("frameworks", [])
    if not frameworks:
        print("No frameworks in file.")
        sys.exit(1)

    now   = datetime.now(timezone.utc)
    start = now - timedelta(hours=args.hours)

    print(f"Endpoint  : {args.endpoint}")
    print(f"Lookback  : {args.hours}h  |  Frameworks: {len(frameworks)}\n")

    results = {}
    for svc in args.services:
        print(f"  {svc} ...", end="", flush=True)
        active = find_frameworks(svc, frameworks, api_key=args.api_key, app_key=args.app_key,
                                 base_url=args.endpoint, start=start, end=now)
        results[svc] = active
        print(f" {active if active else '(none)'}")

    print(f"\n{'SERVICE':<40}  FRAMEWORKS")
    print("-" * 90)
    for svc, fws in results.items():
        print(f"{svc:<40}  {', '.join(fws) if fws else '(none)'}")


if __name__ == "__main__":
    main()
