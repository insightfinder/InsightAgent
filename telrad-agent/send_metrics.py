#!/usr/bin/env python3
"""
Continuously poll BreezeVIEW eNB signal metrics and forward them to InsightFinder.

Metrics sent per attached UE:
  - ulrssi: abs(UlRSSI) in dBm, as a positive value
  - ulcinr: UlCINR in dB

Instance names are per-UE and derived from the eNB-assigned TEID (a small slot number
that is stable for the lifetime of a UE's attachment). The naming scheme is fixed at
design time so instance names never change across restarts.
  Format: ue-{enb_id}-{teid}  (e.g. ue-20-31)
  Component: enb-{enb_id}  (groups all UEs under their serving eNB)

Configuration via .env (same file as get_metrics.py):
  ACCESSPARKS_TELRAD_URL, ACCESSPARKS_TELRAD_USERNAME, ACCESSPARKS_TELRAD_PASSWORD
  INSIGHTFINDER_BASE_URL, INSIGHTFINDER_USER_NAME, INSIGHTFINDER_LICENSE_KEY
  INSIGHTFINDER_PROJECT_NAME, INSIGHTFINDER_SYSTEM_NAME
  INSIGHTFINDER_SAMPLING_INTERVAL  (minutes, default 5)

Usage:
  python3 send_metrics.py               # loop at configured interval
  python3 send_metrics.py --once        # single tick then exit
  python3 send_metrics.py --interval 2  # override interval in minutes
  python3 send_metrics.py --dry-run     # print payload, skip POST
"""

import argparse
import json
import logging
import os
import sys
import time

from get_metrics import collect_metrics, load_env
from insightfinder import Config, InsightFinder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

def build_idm(devices: list[dict], ts_ms: int) -> dict:
    """Transform device results into InsightFinder v2 idm structure.

    One instance per attached UE, keyed by ue-{enb_id}-{teid}.
    UlRSSI (negative dBm) is converted to a positive value via abs().
    UEs missing both metrics are skipped. Unreachable eNBs are skipped entirely.
    """
    idm: dict = {}

    for device in devices:
        if device["status"] != "ok":
            logger.warning(f"Skipping unreachable eNB {device['device_id']}: {device.get('error')}")
            continue

        enb_id = device["device_id"]
        component_name = f"enb-{enb_id}"

        for ue in device.get("ues", []):
            teid = ue.get("teid")
            if teid is None:
                continue

            rssi = ue.get("ul_rssi_dbm")
            cinr = ue.get("ul_cinr_db")
            if rssi is None and cinr is None:
                continue

            instance_name = f"ue-{enb_id}-{teid}"
            metric_points = []
            if rssi is not None:
                metric_points.append({"m": "ulrssi", "v": round(abs(rssi), 2)})
            if cinr is not None:
                metric_points.append({"m": "ulcinr", "v": round(float(cinr), 2)})

            idm[instance_name] = {
                "in": instance_name,
                "cn": component_name,
                "dit": {
                    str(ts_ms): {
                        "t": ts_ms,
                        "metricDataPointSet": metric_points,
                    }
                },
            }

    return idm


def run_tick(
    base_url: str,
    telrad_username: str,
    telrad_password: str,
    timeout: int,
    client: InsightFinder,
    dry_run: bool,
) -> None:
    ts_ms, devices = collect_metrics(base_url, telrad_username, telrad_password, timeout)
    idm = build_idm(devices, ts_ms)

    if not idm:
        logger.warning("No cell data to send this tick")
        return

    if dry_run:
        logger.info("Dry run — payload (not sent):")
        print(json.dumps(idm, indent=2))
        return

    client.send_metric(idm)
    logger.info(f"Sent metrics for {len(idm)} cell instance(s)")


def main():
    parser = argparse.ArgumentParser(description="Send BreezeVIEW signal metrics to InsightFinder")
    parser.add_argument("--once", action="store_true", help="Run a single tick then exit")
    parser.add_argument("--interval", type=float, metavar="MIN", help="Override sampling interval in minutes")
    parser.add_argument("--timeout", type=int, default=15, metavar="SEC", help="BreezeVIEW HTTP timeout (default: 15)")
    parser.add_argument("--dry-run", action="store_true", help="Print payload without sending to InsightFinder")
    args = parser.parse_args()

    env = load_env()

    base_url = (os.environ.get("ACCESSPARKS_TELRAD_URL") or env.get("ACCESSPARKS_TELRAD_URL", "")).rstrip("/")
    telrad_username = os.environ.get("ACCESSPARKS_TELRAD_USERNAME") or env.get("ACCESSPARKS_TELRAD_USERNAME", "")
    telrad_password = os.environ.get("ACCESSPARKS_TELRAD_PASSWORD") or env.get("ACCESSPARKS_TELRAD_PASSWORD", "")

    if not base_url or not telrad_username or not telrad_password:
        print("ERROR: set ACCESSPARKS_TELRAD_URL, ACCESSPARKS_TELRAD_USERNAME, ACCESSPARKS_TELRAD_PASSWORD in .env", file=sys.stderr)
        sys.exit(1)

    if_url = os.environ.get("INSIGHTFINDER_BASE_URL") or env.get("INSIGHTFINDER_BASE_URL", "")
    if_user = os.environ.get("INSIGHTFINDER_USER_NAME") or env.get("INSIGHTFINDER_USER_NAME", "")
    if_key = os.environ.get("INSIGHTFINDER_LICENSE_KEY") or env.get("INSIGHTFINDER_LICENSE_KEY", "")
    if_project = os.environ.get("INSIGHTFINDER_PROJECT_NAME") or env.get("INSIGHTFINDER_PROJECT_NAME", "")
    if_system = os.environ.get("INSIGHTFINDER_SYSTEM_NAME") or env.get("INSIGHTFINDER_SYSTEM_NAME", "")

    if not if_url or not if_user or not if_key or not if_project:
        print("ERROR: set INSIGHTFINDER_BASE_URL, INSIGHTFINDER_USER_NAME, INSIGHTFINDER_LICENSE_KEY, INSIGHTFINDER_PROJECT_NAME in .env", file=sys.stderr)
        sys.exit(1)

    if args.interval is not None:
        interval_minutes = int(args.interval)
    else:
        raw = os.environ.get("INSIGHTFINDER_SAMPLING_INTERVAL") or env.get("INSIGHTFINDER_SAMPLING_INTERVAL", "5")
        interval_minutes = int(raw)
    interval_s = interval_minutes * 60

    logger.info(f"Sampling interval: {interval_minutes} min | InsightFinder project: {if_project}")
    logger.info("Instance naming: ue-{enb_id}-{teid}, component: enb-{enb_id}")

    config = Config(
        url=if_url,
        user_name=if_user,
        license_key=if_key,
        project_name=if_project,
        agent_type="custom",
        instance_type="PrivateCloud",
        system_name=if_system,
        data_type="Metric",
        insight_agent_type="Custom",
        sampling_interval=int(interval_s),
        create_project=True,
    )

    with InsightFinder(config) as client:
        if args.once or args.dry_run:
            run_tick(base_url, telrad_username, telrad_password, args.timeout, client, args.dry_run)
            return

        logger.info("Starting metric loop (Ctrl-C to stop)")
        next_tick = time.monotonic()
        while True:
            next_tick += interval_s
            try:
                run_tick(base_url, telrad_username, telrad_password, args.timeout, client, dry_run=False)
            except Exception as e:
                logger.error(f"Tick failed: {e}")
            sleep_for = max(0.0, next_tick - time.monotonic())
            logger.debug(f"Sleeping {sleep_for:.1f}s until next tick")
            time.sleep(sleep_for)


if __name__ == "__main__":
    main()
