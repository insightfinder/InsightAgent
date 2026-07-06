#!/usr/bin/env python3
"""
Continuously poll BreezeVIEW eNB and CPE signal metrics and forward them to InsightFinder.

Metric sent per eNB (REST NBI) — disabled by default, set ENABLE_ENB_METRICS=true to enable:
  - avg_ulrssi: average abs(UlRSSI) in dBm across all attached UEs

Metrics sent per CPE (BreezeVIEW CLI, optional — see BREEZEVIEW_CLI_* below):
  - UlMCS, DlMCS, UlCINR, UlRSSI: sent as abs() (no averaging) — only the fields a
    given CPE actually reports are included in its payload

Wire format matches the zabbix agent's device-inventory convention (see
getmessages_zabbix.py's convert_to_metric_data()): the instance identifier ("in")
and all metadata (component name, IP, zone, display name) prefer the AccessParks
asset-cache server (a REST cache of Jira Assets / device-inventory data — see
jira_assets.py) when a device resolves to one, packed into a single
JSON-stringified "im" field alongside "in" and "dit" — not sent as direct
cn/z/i keys. Each field falls back to BreezeVIEW's own data only when the
device has no inventory match at all.

Instance identifier priority, per eNB/CPE (see _resolve_instance_id()):
  1. MAC address (device inventory)      → "MAC <mac>"
  2. Serial number (device inventory)    → "SERIAL <serial>"
  3. Object key / Jira key (inventory)   → "JIRAKEY <object_key>"
  4. Native fallback (no inventory match): CPEs fall back to "SERIAL <own serial>"
     (BreezeVIEW's own serial number), then IMSI; eNBs fall back to the BreezeVIEW
     device name, then bare device_id — eNBs have no native MAC/serial to prefix.
A device with no inventory match still sends data (never skipped), just under its
native fallback identifier, with a WARNING log.

"im" metadata packed per instance (all optional, only included when non-empty):
  - cn:  component name — inventory manufacturer-device_class, else the static
         'eNB-Telrad' / 'CPE-Telrad' default
  - idn: display name — the device-inventory's resolved Jira asset label (e.g.
         "Tus-TennisCourt-eNodeB200") when the device matched one; falls back to
         BreezeVIEW's own device_name (eNB) or serial/IMSI (CPE) only when
         unresolved. CPEs have no meaningful native display name of their own
         (BreezeVIEW's is just their serial number, redundant with "in"), so the
         inventory label is what actually makes idn useful.
  - i:   IP address — inventory ip_address; eNBs fall back to BreezeVIEW's own
         device_ip if inventory has none, CPEs do not fall back to their own WAN
         IP (DHCP'd/NAT'd, can be shared/stale)
  - z:   zone — inventory venue only, no native fallback (no BreezeVIEW zone concept)

Per-device and per-CPE inventory mappings are cached in memory (keyed by device_id
and serial number respectively) and only re-queried when a new one appears or a
previously unmapped entry's cooldown expires (1 hour). No asset_map.json file is written.

CLI-based CPE metrics are best-effort: if BREEZEVIEW_CLI_* is not configured, or the CLI
collection fails, the eNB metrics are still sent — see CLAUDE.md for the CLI's strict
metrics-only / never-modify command policy.

Configuration via .env:
  ENABLE_ENB_METRICS  (default: false — required ACCESSPARKS_TELRAD_* only when true)
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

# Per-CPE signal metrics sent to InsightFinder: UL MCS, DL MCS, UL CINR, UL RSSI only
# (field names as parsed by get_cli_metrics.parse_cpe_kpi — see its _NUMERIC_FIELDS).
# One point per field present and numeric for that CPE, sent as abs(value) (no avg);
# a field a given CPE doesn't report is simply omitted from its payload.
_CPE_METRIC_FIELDS = ("UlMCS", "DlMCS", "UlCINR", "UlRSSI")


@dataclass
class JiraState:
    base_url: str
    api_key: str
    # Each asset_map/cpe_asset_map value is
    # {label, venue, component_name, ip, mac, object_key, serial} — see
    # build_asset_map.resolve_with_assets(). All fields but label are "" for
    # entries that fell back to a BreezeVIEW-native name (no Jira match).
    asset_map: dict[str, dict] = field(default_factory=dict)
    unmapped_retry_at: dict[str, float] = field(default_factory=dict)
    cpe_asset_map: dict[str, dict] = field(default_factory=dict)
    cpe_unmapped_retry_at: dict[str, float] = field(default_factory=dict)


def _normalize_mac(mac: str | None) -> str:
    """Mirror the zabbix agent's inv_mac normalization: ':' -> '-', trim leading/
    trailing '-' and whitespace, require at least one alphanumeric character."""
    mac = (mac or "").strip()
    if not mac:
        return ""
    converted = mac.replace(":", "-").strip("-").strip()
    if not converted or not any(c.isalnum() for c in converted):
        return ""
    return converted


def _normalize_serial(serial: str | None) -> str:
    """Mirror the zabbix agent's inv_serial normalization: trim whitespace,
    require at least one alphanumeric character."""
    serial = (serial or "").strip()
    if not serial or not any(c.isalnum() for c in serial):
        return ""
    return serial


def _resolve_instance_id(asset: dict | None, native_fallback: str) -> str:
    """Return the instance identifier ("in"): device-inventory MAC -> Serial ->
    JiraKey (object_key), else native_fallback when the asset has none of those
    (already computed by the caller — e.g. "SERIAL <own serial>" for CPEs, or the
    bare BreezeVIEW device name/id for eNBs, which have no native MAC/serial)."""
    if asset:
        mac = _normalize_mac(asset.get("mac"))
        if mac:
            return f"MAC {mac}"
        serial = _normalize_serial(asset.get("serial"))
        if serial:
            return f"SERIAL {serial}"
        if asset.get("object_key"):
            return f"JIRAKEY {asset['object_key']}"
    return native_fallback


def _pack_im(component_name: str, display_name: str, ip_address: str, zone: str) -> str | None:
    """Pack cn/idn/i/z into a JSON string, matching getmessages_zabbix.py's
    convert_to_metric_data() 'im' (instance metadata) field. Returns None if every
    field is empty, so callers can omit "im" entirely rather than send "{}"."""
    im_data = {}
    if component_name:
        im_data["cn"] = component_name
    if display_name:
        im_data["idn"] = display_name
    if ip_address:
        im_data["i"] = ip_address
    if zone:
        im_data["z"] = zone
    return json.dumps(im_data) if im_data else None


def build_idm(devices: list[dict], ts_ms: int, by_device_id: dict[str, dict]) -> dict:
    """Transform device results into InsightFinder v2 idm structure.

    One instance per eNB. Metric: average abs(UlRSSI) across all attached UEs.
    UEs without UlRSSI data are excluded from the average. eNBs with no UE
    RSSI data are skipped entirely.

    Instance identifier ("in") and metadata packed into "im" (cn/idn/i/z) follow
    the device-inventory-first rules documented in this module's docstring and in
    _resolve_instance_id()/_pack_im(). A device with no inventory match still
    sends data under its native fallback identifier (never skipped), logged as a
    WARNING.
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

        asset = by_device_id.get(enb_id)
        native_name = device.get("device_name") or enb_id
        instance_name = _resolve_instance_id(asset, native_fallback=native_name)
        if not (asset and (asset.get("mac") or asset.get("serial") or asset.get("object_key"))):
            logger.warning(
                f"No device-inventory identifier for eNB {enb_id} — sending under BreezeVIEW name '{instance_name}'"
            )

        component_name = (asset.get("component_name") if asset else "") or COMPONENT_NAME
        zone = (asset.get("venue") if asset else "") or ""
        ip_address = (asset.get("ip") if asset else "") or device.get("device_ip") or ""
        display_name = (asset.get("label") if asset else "") or native_name

        avg_rssi = round(sum(rssi_vals) / len(rssi_vals))

        entry = {
            "in": instance_name,
            "dit": {
                str(ts_ms): {
                    "t": ts_ms,
                    "metricDataPointSet": [{"m": "avg_ulrssi", "v": avg_rssi}],
                }
            },
        }
        im = _pack_im(component_name, display_name, ip_address, zone)
        if im:
            entry["im"] = im
        idm[instance_name] = entry

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


def _cpe_native_fallback(serial: str | None, imsi: str | None) -> str | None:
    """CPE native fallback identifier when there's no device-inventory match:
    "SERIAL <own serial>" (mirroring the netexperience agent's own-serial
    fallback convention), else the bare IMSI, else None."""
    norm = _normalize_serial(serial)
    if norm:
        return f"SERIAL {norm}"
    return imsi or None


def build_cpe_idm(cpes: list[dict], ts_ms: int, by_serial: dict[str, dict]) -> dict:
    """Transform per-CPE KPI dicts (from get_cli_metrics) into InsightFinder v2 idm structure.

    One instance per CPE. Instance identifier ("in") and "im" metadata (cn/idn/i/z)
    follow the device-inventory-first rules in this module's docstring — see
    _resolve_instance_id()/_cpe_native_fallback()/_pack_im(). Offline CPEs and CPEs
    with no usable KPI data are skipped. UlMCS, DlMCS, UlCINR, UlRSSI (see
    _CPE_METRIC_FIELDS) are each sent individually as abs() (no averaging), matching
    the eNB-side convention in build_idm() — a CPE that doesn't report a given field
    simply omits that point.

    IP ("i" in "im") is sent only when the *device-inventory record's* ip_address is
    set — deliberately never the CPE's own current WAN IP, even though that WAN IP is
    now used as a fallback *matching* tier (see refresh_jira_mappings()): WAN IPs are
    DHCP'd/NAT'd and can be shared or stale, fine as a last-resort way to find a
    record but not something we want to report as this CPE's authoritative IP.

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
        asset = by_serial.get(serial) if serial else None
        native_name = serial or cpe.get("IMSI") or ""
        instance_name = _resolve_instance_id(
            asset, native_fallback=_cpe_native_fallback(serial, cpe.get("IMSI"))
        )
        if not instance_name:
            continue
        if not (asset and (asset.get("mac") or asset.get("serial") or asset.get("object_key"))):
            logger.warning(
                f"No device-inventory identifier for CPE {native_name or instance_name} — sending under fallback '{instance_name}'"
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

        component_name = (asset.get("component_name") if asset else "") or CPE_COMPONENT_NAME
        zone = (asset.get("venue") if asset else "") or ""
        ip_address = (asset.get("ip") if asset else "") or ""
        display_name = (asset.get("label") if asset else "") or native_name

        cpe_ts_ms = _cpe_ts_ms(cpe, ts_ms)
        entry = {
            "in": instance_name,
            "dit": {
                str(cpe_ts_ms): {
                    "t": cpe_ts_ms,
                    "metricDataPointSet": points,
                }
            },
        }
        im = _pack_im(component_name, display_name, ip_address, zone)
        if im:
            entry["im"] = im
        idm[instance_name] = entry

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
    asset_map: dict[str, dict],
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
    resolved: dict[str, dict],
    name_map: dict[str, str],
    asset_map: dict[str, dict],
    retry_at: dict[str, float],
    now: float,
) -> None:
    for item_id, entry in resolved.items():
        fallback = name_map.get(item_id) or item_id
        asset_map[item_id] = entry
        if entry["label"] == fallback:
            retry_at[item_id] = now + UNMAPPED_RETRY_S
        else:
            retry_at.pop(item_id, None)


def refresh_jira_mappings(
    devices: list[dict], cpes: list[dict], jira: JiraState
) -> None:
    """Resolve asset names for new/unmapped eNBs and CPEs in one asset-cache lookup.

    eNBs are keyed by device_id and matched by management_ip (device_ip). CPEs are keyed
    and matched by serial_number first, falling back to their current WAN IP (ip-wan)
    only when serial doesn't match — see build_asset_map's match_by="serial" path and
    its ip_fallback_map. Both candidate sets (plus the CPE WAN-IP fallback values) are
    fetched from the asset cache in one fetch_assets() call instead of separate
    round-trips, then resolved independently against the shared result via
    resolve_with_assets().
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
    # WAN-IP fallback values for the same CPE candidate set — cpe_serial_map's keys
    # are serial numbers, so look each one's current ip-wan up directly from cpes.
    cpes_by_serial = {c["serial_number"]: c for c in cpes if c.get("serial_number")}
    cpe_ip_map = {
        key: (cpes_by_serial[key].get("ip-wan") or "")
        for key in cpe_serial_map
        if key in cpes_by_serial
    }

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
        # dict.fromkeys dedupes while preserving order, in case a CPE's WAN IP happens
        # to equal an eNB's management IP already being queried this tick.
        combined_ips = list(dict.fromkeys(
            list(enb_ip_map.values()) + [ip for ip in cpe_ip_map.values() if ip]
        ))
        assets = fetch_assets(
            jira.base_url,
            jira.api_key,
            ips=combined_ips,
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
            cpe_serial_map, assets, cpe_name_map, entity_label="CPE", match_by="serial",
            ip_fallback_map=cpe_ip_map,
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
    enb_enabled: bool = False,
) -> None:
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
    if enb_enabled:
        logger.info(f"Processing eNB metrics via REST NBI ({base_url})...")
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

    enb_enabled = (_cfg(env, "ENABLE_ENB_METRICS") or "false").strip().lower() in ("1", "true", "yes", "on")

    base_url = _cfg(env, "ACCESSPARKS_TELRAD_URL").rstrip("/")
    telrad_username = _cfg(env, "ACCESSPARKS_TELRAD_USERNAME")
    telrad_password = _cfg(env, "ACCESSPARKS_TELRAD_PASSWORD")

    if enb_enabled and (not base_url or not telrad_username or not telrad_password):
        print(
            "ERROR: ENABLE_ENB_METRICS=true requires ACCESSPARKS_TELRAD_URL, "
            "ACCESSPARKS_TELRAD_USERNAME, ACCESSPARKS_TELRAD_PASSWORD in .env",
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
    logger.info(f"eNB REST NBI metric collection: {'enabled' if enb_enabled else 'disabled (set ENABLE_ENB_METRICS=true to enable)'}")
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
        enb_enabled=enb_enabled,
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
