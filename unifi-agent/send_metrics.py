#!/usr/bin/env python3
"""Fetch UniFi AP channel utilization and send to InsightFinder."""

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path

from get_metrics import SUPPORTED_BANDS, collect_ap_rows, list_sites, load_env
from insightfinder import Config, InsightFinder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

_BAD_INSTANCE_CHARS = str.maketrans({c: "-" for c in " ,_@#:"})
_MULTI_DASH = re.compile(r"-{2,}")


def sanitize_name(name: str) -> str:
    """Replace banned chars (space , _ @ # :) with -, collapsing runs."""
    return _MULTI_DASH.sub("-", (name or "unknown").translate(_BAD_INSTANCE_CHARS)).strip("-") or "unknown"


def build_idm(rows: list[dict], ts: int) -> dict:
    ts_str = str(ts)
    idm: dict = {}
    for row in rows:
        band = row["band"]
        if band not in SUPPORTED_BANDS:
            continue

        ip = (row.get("ip") or "").strip()
        ap_name = sanitize_name(row["ap_name"])
        site = row.get("site") or ""
        if not site:
            logger.warning("AP %r has no site name; skipping component name", ap_name)

        instance = sanitize_name(ip) if ip else ap_name
        if instance not in idm:
            entry: dict = {"in": instance, "dit": {ts_str: {"t": ts, "metricDataPointSet": []}}}
            if site:
                entry["cn"] = sanitize_name(site)
            idm[instance] = entry

        mset = idm[instance]["dit"][ts_str]["metricDataPointSet"]
        for metric, val in (
            (f"ChUtil_Busy_{band}", row["ChUtil_Busy"]),
            (f"ChUtil_Rx_{band}", row["ChUtil_Rx"]),
            (f"ChUtil_Tx_{band}", row["ChUtil_Tx"]),
        ):
            if val is not None:
                mset.append({"m": metric, "v": val})

    return {k: v for k, v in idm.items() if v["dit"][ts_str]["metricDataPointSet"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Send UniFi AP metrics to InsightFinder.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print full metric payload before sending.")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    env_path = Path(__file__).parent / ".env"
    env = load_env(env_path)

    def require(var: str) -> str:
        val = env.get(var) or os.environ.get(var)
        if not val:
            raise SystemExit(f"{var} not set in .env or environment.")
        return val

    def optional(var: str, default: str | None = None) -> str | None:
        return env.get(var) or os.environ.get(var) or default

    api_key = require("UNIFI_API_KEY")
    config = Config(
        url=require("INSIGHTFINDER_URL"),
        user_name=require("INSIGHTFINDER_USER_NAME"),
        license_key=require("INSIGHTFINDER_LICENSE_KEY"),
        project_name=require("INSIGHTFINDER_PROJECT_NAME"),
        system_name=optional("INSIGHTFINDER_SYSTEM_NAME"),
        agent_type="Custom",
        data_type="Metric",
        insight_agent_type="Custom",
        instance_type="PrivateCloud",
        sampling_interval=int(optional("INSIGHTFINDER_SAMPLING_INTERVAL", "5")) * 60,
        create_project=True,
    )

    interval = config.sampling_interval

    logger.info("Fetching sites...")
    sites = list_sites(api_key)
    logger.info("Found %d site(s).", len(sites))

    with InsightFinder(config) as client:
        while True:
            ts = int(time.time() * 1000)
            all_rows = collect_ap_rows(api_key, sites=sites)
            idm = build_idm(all_rows, ts)

            if not idm:
                logger.info("No metric data to send.")
            else:
                ts_str = str(ts)
                total_points = sum(len(v["dit"][ts_str]["metricDataPointSet"]) for v in idm.values())
                logger.info("Sending metrics for %d AP instance(s) (%d data points)...", len(idm), total_points)
                if args.verbose:
                    logger.debug("Payload:\n%s", json.dumps(idm, indent=2))
                client.send_metric(idm)
                logger.info("Done. Next run in %d minute(s).", interval // 60)

            elapsed = time.time() - ts / 1000
            time.sleep(max(0, interval - elapsed))


if __name__ == "__main__":
    main()
