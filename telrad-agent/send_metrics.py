#!/usr/bin/env python3
"""
Continuously poll BreezeVIEW eNB signal metrics and forward them to InsightFinder.

Metric sent per eNB:
  - ulrssi: average abs(UlRSSI) in dBm across all attached UEs

One InsightFinder instance per eNB, named after the corresponding Jira asset
(e.g. 'Tus-TennisCourt-eNodeB200'). Instance names are resolved via asset_map.json
(built by build_asset_map.py). If the file is absent at startup it is built
automatically. Fallback: the BreezeVIEW device name (e.g. 'DeathValley-Oasis') with a WARNING log.

Component name is 'eNB-Telrad' for all instances.

Configuration via .env:
  ACCESSPARKS_TELRAD_URL, ACCESSPARKS_TELRAD_USERNAME, ACCESSPARKS_TELRAD_PASSWORD
  INSIGHTFINDER_BASE_URL, INSIGHTFINDER_USER_NAME, INSIGHTFINDER_LICENSE_KEY
  INSIGHTFINDER_PROJECT_NAME, INSIGHTFINDER_SYSTEM_NAME
  INSIGHTFINDER_SAMPLING_INTERVAL  (minutes, default 5)
  ACCESSPARKS_JIRA_URL, ACCESSPARKS_JIRA_USERNAME, ACCESSPARKS_JIRA_API_TOKEN  (for auto-building asset_map.json)

Usage:
  python3 send_metrics.py               # loop at configured interval
  python3 send_metrics.py --once        # single tick then exit
  python3 send_metrics.py --interval 2  # override interval in minutes
  python3 send_metrics.py --dry-run     # print payload, skip POST
  python3 send_metrics.py --rebuild-map # force rebuild asset_map.json then exit
"""

import argparse
import json
import logging
import re
import sys
import time

from build_asset_map import ASSET_MAP_FILE, MAP_STALE_DAYS, build as build_asset_map, map_age_days
from get_metrics import _cfg, collect_metrics, load_env
from insightfinder import Config, InsightFinder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

COMPONENT_NAME = "eNB-Telrad"

_LEADING_SPECIAL = re.compile(r"^[-_\W]+")


def clean_instance_name(name: str) -> str:
    if not name:
        return name
    name = name.replace("_", ".").replace(":", "-")
    cleaned = _LEADING_SPECIAL.sub("", name).strip()
    return cleaned if cleaned else name


def _load_or_build_asset_map(env: dict) -> dict:
    """Return asset_map dict. Auto-builds from Jira if missing or stale."""
    try:
        with open(ASSET_MAP_FILE) as f:
            asset_map = json.load(f)
        age = map_age_days(asset_map)
        if age is not None and age >= MAP_STALE_DAYS:
            logger.info(f"asset_map.json is {age} day(s) old — rebuilding from Jira...")
            try:
                return build_asset_map(env)
            except Exception as e:
                logger.warning(f"Could not rebuild asset map: {e} — continuing with stale map")
        return asset_map
    except FileNotFoundError:
        pass

    logger.info("asset_map.json not found — building automatically from Jira Assets (this may take a moment)...")
    try:
        return build_asset_map(env)
    except Exception as e:
        logger.warning(f"Could not auto-build asset map: {e}  — falling back to device IDs for instance names")
        return {"by_device_id": {}}


def build_idm(devices: list[dict], ts_ms: int, asset_map: dict) -> dict:
    """Transform device results into InsightFinder v2 idm structure.

    One instance per eNB. Metric: average abs(UlRSSI) across all attached UEs.
    UEs without UlRSSI data are excluded from the average. eNBs with no UE
    RSSI data are skipped entirely.
    """
    by_device_id: dict = asset_map.get("by_device_id", {})
    idm: dict = {}

    for device in devices:
        if device["status"] != "ok":
            logger.warning(f"Skipping unreachable eNB {device['device_id']}: {device.get('error')}")
            continue

        enb_id = device["device_id"]
        ues = device.get("ues", [])
        rssi_vals = [abs(u["ul_rssi_dbm"]) for u in ues if u.get("ul_rssi_dbm") is not None]

        if not rssi_vals:
            logger.debug(f"eNB {enb_id}: no UE RSSI data, skipping")
            continue

        instance_name = by_device_id.get(enb_id)
        if not instance_name:
            instance_name = device.get("device_name") or enb_id
            logger.warning(
                f"No asset map entry for eNB {enb_id} — sending under BreezeVIEW name '{instance_name}'"
            )
        instance_name = clean_instance_name(instance_name)

        avg_rssi = round(sum(rssi_vals) / len(rssi_vals))

        idm[instance_name] = {
            "in": instance_name,
            "cn": COMPONENT_NAME,
            "dit": {
                str(ts_ms): {
                    "t": ts_ms,
                    "metricDataPointSet": [{"m": "avg_ulrssi", "v": avg_rssi}],
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
    asset_map: dict,
    dry_run: bool,
) -> None:
    ts_ms, devices = collect_metrics(base_url, telrad_username, telrad_password, timeout)
    idm = build_idm(devices, ts_ms, asset_map)

    if not idm:
        logger.warning("No eNB data to send this tick")
        return

    if dry_run:
        logger.info("Dry run — payload (not sent):")
        print(json.dumps(idm, indent=2))
        return

    client.send_metric(idm)
    logger.info(f"Sent metrics for {len(idm)} eNB instance(s)")


def main():
    parser = argparse.ArgumentParser(description="Send BreezeVIEW eNB average UlRSSI to InsightFinder")
    parser.add_argument("--once", action="store_true", help="Run a single tick then exit")
    parser.add_argument("--interval", type=float, metavar="MIN", help="Override sampling interval in minutes")
    parser.add_argument("--timeout", type=int, default=15, metavar="SEC", help="BreezeVIEW HTTP timeout (default: 15)")
    parser.add_argument("--dry-run", action="store_true", help="Print payload without sending to InsightFinder")
    parser.add_argument("--rebuild-map", action="store_true", help="Force rebuild asset_map.json from Jira then exit")
    args = parser.parse_args()

    env = load_env()

    base_url = _cfg(env, "ACCESSPARKS_TELRAD_URL").rstrip("/")
    telrad_username = _cfg(env, "ACCESSPARKS_TELRAD_USERNAME")
    telrad_password = _cfg(env, "ACCESSPARKS_TELRAD_PASSWORD")

    if not base_url or not telrad_username or not telrad_password:
        print("ERROR: set ACCESSPARKS_TELRAD_URL, ACCESSPARKS_TELRAD_USERNAME, ACCESSPARKS_TELRAD_PASSWORD in .env", file=sys.stderr)
        sys.exit(1)

    if args.rebuild_map:
        build_asset_map(env)
        return

    if_url = _cfg(env, "INSIGHTFINDER_BASE_URL")
    if_user = _cfg(env, "INSIGHTFINDER_USER_NAME")
    if_key = _cfg(env, "INSIGHTFINDER_LICENSE_KEY")
    if_project = _cfg(env, "INSIGHTFINDER_PROJECT_NAME")
    if_system = _cfg(env, "INSIGHTFINDER_SYSTEM_NAME")

    if not if_url or not if_user or not if_key or not if_project:
        print("ERROR: set INSIGHTFINDER_BASE_URL, INSIGHTFINDER_USER_NAME, INSIGHTFINDER_LICENSE_KEY, INSIGHTFINDER_PROJECT_NAME in .env", file=sys.stderr)
        sys.exit(1)

    if args.interval is not None:
        interval_minutes = int(args.interval)
    else:
        raw = _cfg(env, "INSIGHTFINDER_SAMPLING_INTERVAL") or "5"
        interval_minutes = int(raw)
    interval_s = interval_minutes * 60

    asset_map = _load_or_build_asset_map(env)

    logger.info(f"Sampling interval: {interval_minutes} min | InsightFinder project: {if_project}")
    logger.info(f"Component: {COMPONENT_NAME} | Mapped eNBs: {len(asset_map.get('by_device_id', {}))}")

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
            run_tick(base_url, telrad_username, telrad_password, args.timeout, client, asset_map, args.dry_run)
            return

        logger.info("Starting metric loop (Ctrl-C to stop)")
        next_tick = time.monotonic()
        while True:
            next_tick += interval_s
            age = map_age_days(asset_map)
            if age is not None and age >= MAP_STALE_DAYS:
                logger.info(f"asset_map.json is {age} day(s) old — refreshing from Jira...")
                try:
                    asset_map = build_asset_map(env)
                    logger.info(f"Asset map refreshed — {len(asset_map.get('by_device_id', {}))} eNB(s) mapped")
                except Exception as e:
                    logger.warning(f"Asset map refresh failed: {e} — continuing with stale map")
            try:
                run_tick(base_url, telrad_username, telrad_password, args.timeout, client, asset_map, dry_run=False)
            except Exception as e:
                logger.error(f"Tick failed: {e}")
            sleep_for = max(0.0, next_tick - time.monotonic())
            logger.debug(f"Sleeping {sleep_for:.1f}s until next tick")
            time.sleep(sleep_for)


if __name__ == "__main__":
    main()
