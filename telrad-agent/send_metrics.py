#!/usr/bin/env python3
"""
Continuously poll BreezeVIEW eNB and CPE signal metrics and forward them to InsightFinder.

Metric sent per eNB (REST NBI):
  - avg_ulrssi: average abs(UlRSSI) in dBm across all attached UEs

Metrics sent per CPE (BreezeVIEW CLI, optional — see BREEZEVIEW_CLI_* below):
  - RSRP0-3, SINR0-3, RSRQ/RSRQ1-3, CINR0/1, RSSI/RSSI0-3: individual antenna-port
    readings, sent as abs() dBm/dB (no averaging) — only the fields a given CPE
    actually reports are included in its payload

One InsightFinder instance per eNB, named after the corresponding Jira asset
(e.g. 'Tus-TennisCourt-eNodeB200'). One InsightFinder instance per CPE, likewise
named after the corresponding Jira asset when its serial number matches a
serial_number field. Instance names are resolved via the AccessParks asset-cache
server (a REST cache of Jira Assets device data — see jira_assets.py). Per-device
and per-CPE mappings are cached in memory (keyed by device_id and serial number
respectively) and only re-queried when a new one appears or a previously unmapped
entry's cooldown expires (1 hour). No asset_map.json file is written.

Fallback: if the asset cache is unreachable or no asset matches, the BreezeVIEW
device name (e.g. 'DeathValley-Oasis') or CPE serial number (falling back to IMSI)
is used, with a WARNING log.

Component name is 'eNB-Telrad' for eNB instances and 'CPE-Telrad' for per-CPE instances.

CLI-based CPE metrics are best-effort: if BREEZEVIEW_CLI_* is not configured, or the CLI
collection fails, the eNB metrics are still sent — see CLAUDE.md for the CLI's strict
metrics-only / never-modify command policy.

Configuration via .env:
  ACCESSPARKS_TELRAD_URL, ACCESSPARKS_TELRAD_USERNAME, ACCESSPARKS_TELRAD_PASSWORD
  INSIGHTFINDER_BASE_URL, INSIGHTFINDER_USER_NAME, INSIGHTFINDER_LICENSE_KEY
  INSIGHTFINDER_PROJECT_NAME, INSIGHTFINDER_SYSTEM_NAME
  INSIGHTFINDER_SAMPLING_INTERVAL  (minutes, default 5)
  ASSET_CACHE_URL, ASSET_CACHE_API_KEY
  BREEZEVIEW_CLI_HOST, BREEZEVIEW_CLI_PORT, BREEZEVIEW_CLI_USER,
  BREEZEVIEW_CLI_PASSWORD, BREEZEVIEW_CLI_SNAPSHOT_TIMEOUT, BREEZEVIEW_CLI_POLL_INTERVAL

Usage:
  python3 send_metrics.py               # loop at configured interval
  python3 send_metrics.py --once        # single tick then exit
  python3 send_metrics.py --interval 2  # override interval in minutes
  python3 send_metrics.py --dry-run     # print payload, skip POST
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from build_asset_map import resolve_with_assets
from get_cli_metrics import collect_cpe_metrics
from get_metrics import _cfg, collect_metrics, load_env
from insightfinder import Config, InsightFinder
from jira_assets import fetch_assets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

COMPONENT_NAME = "eNB-Telrad"
CPE_COMPONENT_NAME = "CPE-Telrad"
UNMAPPED_RETRY_S = 3600

# Per-CPE signal metrics sent to InsightFinder, one point per field present and numeric
# for that CPE, sent as abs(value) (no avg). Fields not reported by a given CPE
# (e.g. RSRP2/3 on a 2-antenna device) are simply omitted from its payload.
_CPE_METRIC_FIELDS = (
    "RSRP0", "RSRP1", "RSRP2", "RSRP3",
    "SINR0", "SINR1", "SINR2", "SINR3",
    "RSRQ", "RSRQ1", "RSRQ2", "RSRQ3",
    "CINR0", "CINR1",
    "RSSI", "RSSI0", "RSSI1", "RSSI2", "RSSI3",
)


@dataclass
class JiraState:
    base_url: str
    api_key: str
    asset_map: dict[str, str] = field(default_factory=dict)
    unmapped_retry_at: dict[str, float] = field(default_factory=dict)
    cpe_asset_map: dict[str, str] = field(default_factory=dict)
    cpe_unmapped_retry_at: dict[str, float] = field(default_factory=dict)


def build_idm(devices: list[dict], ts_ms: int, by_device_id: dict[str, str]) -> dict:
    """Transform device results into InsightFinder v2 idm structure.

    One instance per eNB. Metric: average abs(UlRSSI) across all attached UEs.
    UEs without UlRSSI data are excluded from the average. eNBs with no UE
    RSSI data are skipped entirely.
    """
    idm: dict = {}

    for device in devices:
        if device["status"] != "ok":
            logger.warning(
                f"Skipping unreachable eNB {device['device_id']}: {device.get('error')}"
            )
            continue

        enb_id = device["device_id"]
        ues = device.get("ues", [])
        rssi_vals = [
            abs(u["ul_rssi_dbm"]) for u in ues if u.get("ul_rssi_dbm") is not None
        ]

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


_SUB_SECOND_RE = re.compile(r"\.(\d{1,6})(?=[Z+-]|$)")


def _pad_fractional_seconds(raw: str) -> str:
    """Zero-pad a sub-second field to 6 digits.

    BreezeVIEW's CLI emits collection-date with 1-2 fractional digits (e.g.
    '...33.9+00:00'), which datetime.fromisoformat() only accepts as-is on
    Python 3.11+; earlier versions require exactly 3 or 6 digits.
    """
    return _SUB_SECOND_RE.sub(lambda m: "." + m.group(1).ljust(6, "0"), raw, count=1)


def _cpe_ts_ms(cpe: dict, fallback_ts_ms: int) -> int:
    """Resolve a CPE's own collection-date (from the CLI) to epoch ms.

    Falls back to the tick's fetch-completion timestamp if collection-date is
    missing or fails to parse, so a single malformed record can't drop metrics.
    """
    raw = cpe.get("collection-date")
    if not raw:
        return fallback_ts_ms
    try:
        return int(datetime.fromisoformat(_pad_fractional_seconds(raw)).timestamp() * 1000)
    except ValueError:
        logger.warning(f"Could not parse collection-date {raw!r} — using fetch-completion timestamp")
        return fallback_ts_ms


def build_cpe_idm(cpes: list[dict], ts_ms: int, by_serial: dict[str, str]) -> dict:
    """Transform per-CPE KPI dicts (from get_cli_metrics) into InsightFinder v2 idm structure.

    One instance per CPE, named after the corresponding Jira asset when the CPE's
    serial number has been resolved (see refresh_jira_mappings()); falls back to the
    BreezeVIEW serial number, then IMSI, when unresolved. Offline CPEs and CPEs with
    no usable KPI data are skipped. RSRP0-3, SINR0-3, RSRQ/RSRQ1-3, CINR0/1, and
    RSSI/RSSI0-3 are each sent individually as abs() dBm/dB (no averaging), matching
    the eNB-side convention in build_idm() — a CPE that doesn't report a given
    antenna-port field simply omits that point.

    Each CPE's timestamp is its own collection-date reported by the CLI (per-CPE, since
    the network-wide snapshot completes each device's KPI read at a slightly different
    moment), not the tick's overall fetch-completion time; ts_ms is used only as a
    fallback when a record's collection-date is missing or unparseable.

    If two CPEs resolve to the same instance name (e.g. a shared/stale WAN IP maps
    both to the same Jira asset), the second one is skipped with a WARNING rather
    than silently overwriting the first's metrics in the output payload.
    """
    idm: dict = {}

    for cpe in cpes:
        if cpe.get("ue-status") != "online":
            continue

        serial = cpe.get("serial_number")
        resolved_name = by_serial.get(serial) if serial else None
        instance_name = resolved_name or serial or cpe.get("IMSI")
        if not instance_name:
            continue
        if not resolved_name:
            logger.warning(
                f"No asset map entry for CPE {instance_name} — sending under BreezeVIEW name '{instance_name}'"
            )

        if instance_name in idm:
            logger.warning(
                f"CPE {serial or cpe.get('IMSI')} resolved to instance name '{instance_name}', which is already "
                "in use by another CPE this tick — skipping to avoid overwriting its metrics"
            )
            continue

        points = [
            {"m": f, "v": abs(cpe[f])}
            for f in _CPE_METRIC_FIELDS
            if isinstance(cpe.get(f), (int, float))
        ]

        if not points:
            logger.debug(f"CPE {instance_name}: no usable KPI data, skipping")
            continue

        cpe_ts_ms = _cpe_ts_ms(cpe, ts_ms)
        idm[instance_name] = {
            "in": instance_name,
            "cn": CPE_COMPONENT_NAME,
            "dit": {
                str(cpe_ts_ms): {
                    "t": cpe_ts_ms,
                    "metricDataPointSet": points,
                }
            },
        }

    return idm


def _prune_stale_retries(active_ids: set[str], retry_at: dict[str, float]) -> None:
    for stale in list(retry_at):
        if stale not in active_ids:
            retry_at.pop(stale)


def _select_candidates(
    items: list[dict],
    id_key: str,
    ip_key: str,
    is_eligible,
    asset_map: dict[str, str],
    retry_at: dict[str, float],
    now: float,
    name_key: str | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Return ({id: ip}, {id: fallback_name}) for items unmapped or past their retry cooldown.

    name_key selects which field holds the BreezeVIEW fallback display name; if None,
    the id itself is used as the fallback name (e.g. a CPE serial number).
    """
    ip_map: dict[str, str] = {}
    name_map: dict[str, str] = {}
    for item in items:
        item_id = item.get(id_key)
        if not item_id or not is_eligible(item):
            continue
        if item_id in asset_map and now < retry_at.get(item_id, float("inf")):
            continue
        ip_map[item_id] = item.get(ip_key) or ""
        name_map[item_id] = (item.get(name_key, "") if name_key else item_id) or item_id
    return ip_map, name_map


def _apply_resolution(
    resolved: dict[str, str],
    name_map: dict[str, str],
    asset_map: dict[str, str],
    retry_at: dict[str, float],
    now: float,
) -> None:
    for item_id, label in resolved.items():
        fallback = name_map.get(item_id) or item_id
        asset_map[item_id] = label
        if label == fallback:
            retry_at[item_id] = now + UNMAPPED_RETRY_S
        else:
            retry_at.pop(item_id, None)


def refresh_jira_mappings(
    devices: list[dict], cpes: list[dict], jira: JiraState
) -> None:
    """Resolve asset names for new/unmapped eNBs and CPEs in one asset-cache lookup.

    eNBs are keyed by device_id and matched by management_ip (device_ip). CPEs are keyed
    and matched by serial_number only (no WAN-IP fallback — see build_asset_map's
    match_by="serial" path). Both candidate sets are fetched from the asset cache in one
    fetch_assets() call instead of two separate round-trips, then resolved independently
    against the shared result via resolve_with_assets().
    """
    now = time.monotonic()
    _prune_stale_retries(
        {d["device_id"] for d in devices if d.get("device_id")}, jira.unmapped_retry_at
    )
    _prune_stale_retries(
        {c["serial_number"] for c in cpes if c.get("serial_number")},
        jira.cpe_unmapped_retry_at,
    )

    enb_ip_map, enb_name_map = _select_candidates(
        devices,
        "device_id",
        "device_ip",
        lambda d: d.get("status") == "ok",
        jira.asset_map,
        jira.unmapped_retry_at,
        now,
        name_key="device_name",
    )
    cpe_serial_map, cpe_name_map = _select_candidates(
        cpes,
        "serial_number",
        "serial_number",
        lambda c: c.get("ue-status") == "online",
        jira.cpe_asset_map,
        jira.cpe_unmapped_retry_at,
        now,
    )

    if not enb_ip_map and not cpe_serial_map:
        return

    if enb_ip_map:
        logger.info(
            f"Querying asset cache for {len(enb_ip_map)} new/unmapped eNB(s): {list(enb_ip_map)}"
        )
    if cpe_serial_map:
        logger.info(
            f"Querying asset cache for {len(cpe_serial_map)} new/unmapped CPE(s): {list(cpe_serial_map)}"
        )

    try:
        assets = fetch_assets(
            jira.base_url,
            jira.api_key,
            ips=list(enb_ip_map.values()),
            serials=list(cpe_serial_map.values()),
        )
    except Exception as e:
        logger.warning(
            f"Asset cache lookup failed for new device(s)/CPE(s): {e} — will retry next tick"
        )
        return

    if enb_ip_map:
        resolved = resolve_with_assets(
            enb_ip_map, assets, enb_name_map, entity_label="eNB"
        )
        _apply_resolution(
            resolved, enb_name_map, jira.asset_map, jira.unmapped_retry_at, now
        )
    if cpe_serial_map:
        resolved = resolve_with_assets(
            cpe_serial_map, assets, cpe_name_map, entity_label="CPE", match_by="serial"
        )
        _apply_resolution(
            resolved, cpe_name_map, jira.cpe_asset_map, jira.cpe_unmapped_retry_at, now
        )


def run_tick(
    base_url: str,
    telrad_username: str,
    telrad_password: str,
    timeout: int,
    client: InsightFinder,
    jira: JiraState,
    dry_run: bool,
    cli_config: dict | None = None,
) -> None:
    logger.info(f"Processing eNB metrics via REST NBI ({base_url})...")

    cpe_result = {}
    cpe_thread = None
    if cli_config:
        logger.info(
            f"Processing CPE metrics via BreezeVIEW CLI ({cli_config['host']}:{cli_config['port']})..."
        )

        def _collect_cpe():
            try:
                cpe_result["ts_ms"], cpe_result["cpes"] = collect_cpe_metrics(
                    cli_config["host"],
                    cli_config["port"],
                    cli_config["user"],
                    cli_config["password"],
                    timeout=timeout,
                    snapshot_timeout=cli_config["snapshot_timeout"],
                    poll_interval=cli_config["poll_interval"],
                )
            except Exception as e:
                cpe_result["error"] = e

        cpe_thread = threading.Thread(target=_collect_cpe, daemon=True)
        cpe_thread.start()

    ts_ms, devices = None, []
    try:
        ts_ms, devices = collect_metrics(
            base_url, telrad_username, telrad_password, timeout
        )
    except Exception as e:
        logger.error(
            f"eNB REST metric collection FAILED ({base_url}): {type(e).__name__}: {e}"
        )

    cpe_ts_ms, cpes = None, []
    if cpe_thread is not None:
        cpe_thread.join()
        if "error" in cpe_result:
            e = cpe_result["error"]
            logger.error(
                f"CLI CPE metric collection FAILED ({cli_config['host']}:{cli_config['port']}): {type(e).__name__}: {e}"
            )
        else:
            cpe_ts_ms = cpe_result.get("ts_ms")
            cpes = cpe_result.get("cpes", [])

    refresh_jira_mappings(devices, cpes, jira)

    idm = build_idm(devices, ts_ms, jira.asset_map)
    enb_count = len(idm)

    cpe_count = 0
    if cpes:
        try:
            cpe_idm = build_cpe_idm(cpes, cpe_ts_ms, jira.cpe_asset_map)
            cpe_count = len(cpe_idm)
            idm.update(cpe_idm)
        except Exception as e:
            logger.warning(f"CPE asset resolution/metric build failed this tick: {e}")

    if not idm:
        logger.warning("No eNB or CPE data to send this tick")
        return

    if dry_run:
        logger.info("Dry run — payload (not sent):")
        print(json.dumps(idm, indent=2))
        return

    client.send_metric(idm)
    logger.info(
        f"Sent metrics for {enb_count} eNB instance(s) and {cpe_count} CPE instance(s)"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Send BreezeVIEW eNB average UlRSSI to InsightFinder"
    )
    parser.add_argument(
        "--once", action="store_true", help="Run a single tick then exit"
    )
    parser.add_argument(
        "--interval",
        type=float,
        metavar="MIN",
        help="Override sampling interval in minutes",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        metavar="SEC",
        help="BreezeVIEW HTTP timeout (default: 15)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload without sending to InsightFinder",
    )
    args = parser.parse_args()

    env = load_env()

    base_url = _cfg(env, "ACCESSPARKS_TELRAD_URL").rstrip("/")
    telrad_username = _cfg(env, "ACCESSPARKS_TELRAD_USERNAME")
    telrad_password = _cfg(env, "ACCESSPARKS_TELRAD_PASSWORD")

    if not base_url or not telrad_username or not telrad_password:
        print(
            "ERROR: set ACCESSPARKS_TELRAD_URL, ACCESSPARKS_TELRAD_USERNAME, ACCESSPARKS_TELRAD_PASSWORD in .env",
            file=sys.stderr,
        )
        sys.exit(1)

    if_url = _cfg(env, "INSIGHTFINDER_BASE_URL")
    if_user = _cfg(env, "INSIGHTFINDER_USER_NAME")
    if_key = _cfg(env, "INSIGHTFINDER_LICENSE_KEY")
    if_project = _cfg(env, "INSIGHTFINDER_PROJECT_NAME")
    if_system = _cfg(env, "INSIGHTFINDER_SYSTEM_NAME")

    if not if_url or not if_user or not if_key or not if_project:
        print(
            "ERROR: set INSIGHTFINDER_BASE_URL, INSIGHTFINDER_USER_NAME, INSIGHTFINDER_LICENSE_KEY, INSIGHTFINDER_PROJECT_NAME in .env",
            file=sys.stderr,
        )
        sys.exit(1)

    asset_cache_url = _cfg(env, "ASSET_CACHE_URL")
    asset_cache_key = _cfg(env, "ASSET_CACHE_API_KEY")

    if not asset_cache_url or not asset_cache_key:
        print(
            "WARNING: asset cache config incomplete — asset names will fall back to BreezeVIEW device names",
            file=sys.stderr,
        )

    cli_host = _cfg(env, "BREEZEVIEW_CLI_HOST")
    cli_user = _cfg(env, "BREEZEVIEW_CLI_USER")
    cli_password = _cfg(env, "BREEZEVIEW_CLI_PASSWORD")
    cli_config = None
    if cli_host and cli_user and cli_password:
        cli_config = {
            "host": cli_host,
            "port": _cfg(env, "BREEZEVIEW_CLI_PORT") or "22",
            "user": cli_user,
            "password": cli_password,
            "snapshot_timeout": int(
                _cfg(env, "BREEZEVIEW_CLI_SNAPSHOT_TIMEOUT") or "240"
            ),
            "poll_interval": int(_cfg(env, "BREEZEVIEW_CLI_POLL_INTERVAL") or "10"),
        }
    else:
        print(
            "WARNING: BREEZEVIEW_CLI_* config incomplete — skipping CPE KPI collection via CLI",
            file=sys.stderr,
        )

    if args.interval is not None:
        interval_minutes = int(args.interval)
    else:
        raw = _cfg(env, "INSIGHTFINDER_SAMPLING_INTERVAL") or "5"
        interval_minutes = int(raw)
    interval_s = interval_minutes * 60

    jira = JiraState(base_url=asset_cache_url, api_key=asset_cache_key)

    logger.info(
        f"Sampling interval: {interval_minutes} min | InsightFinder project: {if_project}"
    )
    logger.info(f"Components: {COMPONENT_NAME}, {CPE_COMPONENT_NAME}")
    logger.info(f"CLI CPE metric collection: {'enabled' if cli_config else 'disabled'}")

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
        cli_config=cli_config,
    )

    with InsightFinder(config) as client:
        if args.once or args.dry_run:
            run_tick(client=client, dry_run=args.dry_run, **tick_kwargs)
            return

        logger.info("Starting metric loop (Ctrl-C to stop)")
        next_tick = time.monotonic()
        tick_num = 0
        while True:
            tick_num += 1
            next_tick += interval_s
            logger.info(f"Tick #{tick_num} starting")
            try:
                run_tick(client=client, dry_run=False, **tick_kwargs)
            except Exception as e:
                logger.error(f"Tick #{tick_num} failed: {e}")
            sleep_for = max(0.0, next_tick - time.monotonic())
            next_tick_at = time.strftime(
                "%H:%M:%S", time.localtime(time.time() + sleep_for)
            )
            logger.info(f"Next tick at {next_tick_at} (in {sleep_for:.0f}s)")
            time.sleep(sleep_for)


if __name__ == "__main__":
    main()
