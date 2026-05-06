#!/usr/bin/env python3
"""
Continuously poll BreezeVIEW eNB signal metrics and forward them to InsightFinder.

Metric sent per eNB:
  - ulrssi: average abs(UlRSSI) in dBm across all attached UEs

One InsightFinder instance per eNB, named after the corresponding Jira asset
(e.g. 'Tus-TennisCourt-eNodeB200'). Instance names are resolved via a live Jira
Assets query. The Jira workspace ID is fetched once at startup. Per-device mappings
are cached in memory and only re-queried when a new device_id appears or a previously
unmapped device's cooldown expires (1 hour). No asset_map.json file is written.

Fallback: if Jira is unreachable, the BreezeVIEW device name (e.g. 'DeathValley-Oasis')
is used with a WARNING log.

Component name is 'eNB-Telrad' for all instances.

Configuration via .env:
  ACCESSPARKS_TELRAD_URL, ACCESSPARKS_TELRAD_USERNAME, ACCESSPARKS_TELRAD_PASSWORD
  INSIGHTFINDER_BASE_URL, INSIGHTFINDER_USER_NAME, INSIGHTFINDER_LICENSE_KEY
  INSIGHTFINDER_PROJECT_NAME, INSIGHTFINDER_SYSTEM_NAME
  INSIGHTFINDER_SAMPLING_INTERVAL  (minutes, default 5)
  ACCESSPARKS_JIRA_URL, ACCESSPARKS_JIRA_USERNAME, ACCESSPARKS_JIRA_API_TOKEN

Usage:
  python3 send_metrics.py               # loop at configured interval
  python3 send_metrics.py --once        # single tick then exit
  python3 send_metrics.py --interval 2  # override interval in minutes
  python3 send_metrics.py --dry-run     # print payload, skip POST
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field

from build_asset_map import resolve_subset
from get_metrics import _cfg, collect_metrics, load_env
from insightfinder import Config, InsightFinder
from jira_assets import discover_workspace_id

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

COMPONENT_NAME = "eNB-Telrad"
UNMAPPED_RETRY_S = 3600


@dataclass
class JiraState:
    url: str
    user: str
    token: str
    workspace_id: str | None = None
    asset_map: dict[str, str] = field(default_factory=dict)
    unmapped_retry_at: dict[str, float] = field(default_factory=dict)


def build_idm(devices: list[dict], ts_ms: int, by_device_id: dict[str, str]) -> dict:
    """Transform device results into InsightFinder v2 idm structure.

    One instance per eNB. Metric: average abs(UlRSSI) across all attached UEs.
    UEs without UlRSSI data are excluded from the average. eNBs with no UE
    RSSI data are skipped entirely.
    """
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


def _try_discover_workspace(jira: JiraState) -> None:
    try:
        jira.workspace_id = discover_workspace_id(jira.url, jira.user, jira.token)
    except Exception as e:
        logger.warning(f"Jira workspace discovery failed: {e} — will retry each tick")


def refresh_new_devices(devices: list[dict], jira: JiraState) -> None:
    """Query Jira for device_ids not yet in asset_map (or whose retry cooldown expired)."""
    if jira.workspace_id is None:
        _try_discover_workspace(jira)
    if jira.workspace_id is None:
        return

    active_ids = {d["device_id"] for d in devices}
    for stale in list(jira.unmapped_retry_at):
        if stale not in active_ids:
            jira.unmapped_retry_at.pop(stale)

    now = time.monotonic()
    candidates = [
        d for d in devices
        if d.get("status") == "ok"
        and (
            d["device_id"] not in jira.asset_map
            or now >= jira.unmapped_retry_at.get(d["device_id"], float("inf"))
        )
    ]
    if not candidates:
        return

    candidate_ip_map = {d["device_id"]: d.get("device_ip", "") for d in candidates}
    candidate_name_map = {d["device_id"]: d.get("device_name", "") for d in candidates}

    logger.info(f"Querying Jira for {len(candidates)} new/unmapped eNB(s): {list(candidate_ip_map)}")
    try:
        resolved = resolve_subset(jira.user, jira.token, jira.workspace_id, candidate_ip_map, candidate_name_map)
    except Exception as e:
        logger.warning(f"Jira asset lookup failed for new device(s): {e} — will retry next tick")
        return

    for device_id, label in resolved.items():
        bv_name = candidate_name_map.get(device_id) or device_id
        jira.asset_map[device_id] = label
        if label == bv_name:
            jira.unmapped_retry_at[device_id] = now + UNMAPPED_RETRY_S
        else:
            jira.unmapped_retry_at.pop(device_id, None)


def run_tick(
    base_url: str,
    telrad_username: str,
    telrad_password: str,
    timeout: int,
    client: InsightFinder,
    jira: JiraState,
    dry_run: bool,
) -> None:
    ts_ms, devices = collect_metrics(base_url, telrad_username, telrad_password, timeout)

    refresh_new_devices(devices, jira)

    idm = build_idm(devices, ts_ms, jira.asset_map)

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
    args = parser.parse_args()

    env = load_env()

    base_url = _cfg(env, "ACCESSPARKS_TELRAD_URL").rstrip("/")
    telrad_username = _cfg(env, "ACCESSPARKS_TELRAD_USERNAME")
    telrad_password = _cfg(env, "ACCESSPARKS_TELRAD_PASSWORD")

    if not base_url or not telrad_username or not telrad_password:
        print("ERROR: set ACCESSPARKS_TELRAD_URL, ACCESSPARKS_TELRAD_USERNAME, ACCESSPARKS_TELRAD_PASSWORD in .env", file=sys.stderr)
        sys.exit(1)

    if_url = _cfg(env, "INSIGHTFINDER_BASE_URL")
    if_user = _cfg(env, "INSIGHTFINDER_USER_NAME")
    if_key = _cfg(env, "INSIGHTFINDER_LICENSE_KEY")
    if_project = _cfg(env, "INSIGHTFINDER_PROJECT_NAME")
    if_system = _cfg(env, "INSIGHTFINDER_SYSTEM_NAME")

    if not if_url or not if_user or not if_key or not if_project:
        print("ERROR: set INSIGHTFINDER_BASE_URL, INSIGHTFINDER_USER_NAME, INSIGHTFINDER_LICENSE_KEY, INSIGHTFINDER_PROJECT_NAME in .env", file=sys.stderr)
        sys.exit(1)

    jira_url = _cfg(env, "ACCESSPARKS_JIRA_URL")
    jira_user = _cfg(env, "ACCESSPARKS_JIRA_USERNAME")
    jira_token = _cfg(env, "ACCESSPARKS_JIRA_API_TOKEN")

    if not jira_url or not jira_user or not jira_token:
        print("WARNING: Jira config incomplete — asset names will fall back to BreezeVIEW device names", file=sys.stderr)

    if args.interval is not None:
        interval_minutes = int(args.interval)
    else:
        raw = _cfg(env, "INSIGHTFINDER_SAMPLING_INTERVAL") or "5"
        interval_minutes = int(raw)
    interval_s = interval_minutes * 60

    jira = JiraState(url=jira_url, user=jira_user, token=jira_token)
    _try_discover_workspace(jira)

    logger.info(f"Sampling interval: {interval_minutes} min | InsightFinder project: {if_project}")
    logger.info(f"Component: {COMPONENT_NAME} | Jira workspace: {jira.workspace_id or 'pending'}")

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

    tick_kwargs = dict(
        base_url=base_url,
        telrad_username=telrad_username,
        telrad_password=telrad_password,
        timeout=args.timeout,
        jira=jira,
    )

    with InsightFinder(config) as client:
        if args.once or args.dry_run:
            run_tick(client=client, dry_run=args.dry_run, **tick_kwargs)
            return

        logger.info("Starting metric loop (Ctrl-C to stop)")
        next_tick = time.monotonic()
        while True:
            next_tick += interval_s
            try:
                run_tick(client=client, dry_run=False, **tick_kwargs)
            except Exception as e:
                logger.error(f"Tick failed: {e}")
            sleep_for = max(0.0, next_tick - time.monotonic())
            logger.debug(f"Sleeping {sleep_for:.1f}s until next tick")
            time.sleep(sleep_for)


if __name__ == "__main__":
    main()
