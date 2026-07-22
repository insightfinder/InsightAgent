#!/usr/bin/env python3
"""Fetch UniFi AP 5GHz metrics and send to InsightFinder."""

import argparse
import datetime
import importlib.util
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from ap_inventory_lookup import atomic_write_json, resolve_ap
from get_metrics import SUPPORTED_BANDS, collect_ap_rows, list_sites, load_env
from insightfinder import Config, InsightFinder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

_PLACEHOLDER_VALUES = {"", "n/a", "na", "none", "null", "unknown", "tbd", "-"}


def load_derived_metrics(script_path: str | None) -> list:
    if not script_path:
        return []
    path = Path(script_path)
    if not path.exists():
        logger.warning("DERIVED_METRICS_SCRIPT not found: %s", script_path)
        return []
    spec = importlib.util.spec_from_file_location("_derived_metrics", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rules = getattr(mod, "DERIVED_METRICS", [])
    logger.info("Loaded %d derived metric rule(s) from %s", len(rules), path)
    return rules


def apply_derived_metrics(tags: dict, metrics: dict, rules: list) -> list[tuple]:
    """Evaluate each rule; return (name, value) pairs for rules that fire."""
    results = []
    for rule in rules:
        try:
            if rule["condition"](tags, metrics):
                results.append((rule["name"], rule["value_if_true"]))
            elif "value_if_false" in rule:
                results.append((rule["name"], rule["value_if_false"]))
        except (KeyError, ValueError, TypeError):
            pass
    return results


def load_ap_lookup(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return {k: v for k, v in data.items() if k != "lastmodifiedtimedata"}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def load_ap_not_found(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def load_lastmodified(path: Path) -> str:
    try:
        return json.loads(path.read_text()).get("lastmodifiedtimedata", "")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return ""


def resolve_new_aps(
    rows: list[dict], ap_lookup: dict, ap_not_found: dict,
    base_url: str, api_key: str, lookup_path: Path, not_found_path: Path,
) -> set[str]:
    """Look up any AP seen for the first time immediately, rather than waiting
    for the once-daily inventory refresh window - a device seen for the first
    time must be looked up right away, not stream under its bare own name
    until the next scheduled refresh happens to come around. Mutates
    ap_lookup/ap_not_found in place and persists both files if anything
    changed.

    Returns the set of macs that errored this cycle (API/network error, so no
    conclusive answer yet) - the caller MUST exclude these from this cycle's
    build_idm() rather than falling back to their own name: a device that has
    never actually been through a completed Inventory lookup is not the same
    as one Inventory has confirmed it doesn't have, and must not be sent under
    any identity until an actual lookup attempt resolves it one way or the
    other."""
    seen: set[str] = set()
    pending: set[str] = set()
    changed = False
    for row in rows:
        mac = (row.get("ap_mac") or "").lower()
        if not mac or mac in seen or mac in ap_lookup or mac in ap_not_found:
            continue
        seen.add(mac)
        ap_stub = {
            "mac": mac,
            "serial": row.get("ap_serial") or "",
            "name": row.get("ap_name") or "",
            "ip": row.get("ip") or "",
        }
        ap_key, matched_entry, had_error = resolve_ap(ap_stub, base_url, api_key)
        if had_error:
            # API/network error, not a confirmed miss - stays unresolved so
            # it's retried next cycle rather than being recorded as not-found
            # (and excluded from sending this cycle - see docstring above).
            pending.add(mac)
            logger.warning("Inventory: API error resolving new AP %s - will retry next cycle", mac)
            continue
        if matched_entry:
            ap_lookup[ap_key] = matched_entry
            logger.info("Inventory: resolved new AP %s via %r", mac, matched_entry["identifier_used"])
        else:
            ap_not_found[ap_key] = {"ap": ap_stub}
            logger.info("Inventory: new AP %s not found in Inventory", mac)
        changed = True

    if changed:
        # Preserve whatever full-refresh timestamp is currently on disk -
        # incremental saves must never advance it, or the once-daily full
        # refresh (which revalidates existing matches and retries misses)
        # would never fire again today.
        payload = dict(ap_lookup)
        last_modified = load_lastmodified(lookup_path)
        if last_modified:
            payload["lastmodifiedtimedata"] = last_modified
        atomic_write_json(lookup_path, payload)
        atomic_write_json(not_found_path, ap_not_found)

    return pending


def _is_placeholder(value: str) -> bool:
    """Recognizes the inventory's various "no data" conventions the same way
    devicelookup.go's isPlaceholder does: known placeholder words, plus any
    value with no letter/digit at all."""
    trimmed = (value or "").strip()
    if trimmed.lower() in _PLACEHOLDER_VALUES:
        return True
    return not any(c.isalnum() for c in trimmed)


def inv_field(d: dict, key: str) -> str:
    """Read a string field from an Inventory dict, treating placeholders as missing."""
    v = (d or {}).get(key)
    if not isinstance(v, str) or _is_placeholder(v):
        return ""
    return v


def normalize_mac(mac: str) -> str:
    """':' -> '-', trim leading/trailing '-'. No case conversion."""
    mac = (mac or "").strip()
    if not mac:
        return ""
    converted = mac.replace(":", "-").strip("-")
    return converted if any(c.isalnum() for c in converted) else ""


def clean_own_name(name: str) -> str:
    """'_' and ':' both -> '-' (matches devicelookup.go's CleanOwnName)."""
    name = (name or "").strip()
    if not name:
        return ""
    return name.replace("_", "-").replace(":", "-").strip("-")


def build_instance_name(devices: dict, own_name: str) -> str | None:
    """Instance name preference: Inventory MAC > Inventory serial > Inventory
    object_key > the AP's own name (cleaned). Returns None if none of these are
    available - the caller must drop the AP rather than send it under any
    other fallback identifier. No uppercase/lowercase conversion anywhere."""
    inv_mac = normalize_mac(inv_field(devices, "mac_address"))
    if inv_mac:
        return f"MAC {inv_mac}"
    inv_serial = inv_field(devices, "serial_number")
    if inv_serial:
        return f"SERIAL {inv_serial}"
    inv_object_key = inv_field(devices, "object_key")
    if inv_object_key:
        return f"JIRAKEY {inv_object_key}"
    cleaned_own = clean_own_name(own_name)
    if cleaned_own:
        return cleaned_own
    return None


def component_name_from_lookup(devices: dict) -> str:
    """Return 'Manufacturer-DeviceClass' from the matched Inventory record, or
    empty string. Only set when both are present in Inventory - no default."""
    model = (devices or {}).get("model") or {}
    manufacturer = inv_field(model, "manufacturer")
    device_class = inv_field(model, "device_class")
    if manufacturer and device_class:
        return f"{manufacturer}-{device_class}"
    return ""


def maybe_refresh_ap_lookup(script_path: Path, lookup_path: Path) -> bool:
    """Run ap_inventory_lookup.py once per day during the 00:00–00:20 UTC window.
    Reads lastmodifiedtimedata from aplookup.json to skip if already run today. Never raises.
    Returns True if a refresh was executed."""
    now = datetime.datetime.now(datetime.timezone.utc)
    if not (now.hour == 0 and now.minute < 20):
        return False
    try:
        data = json.loads(lookup_path.read_text())
        ts = data.get("lastmodifiedtimedata", "")
        if ts and datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").date() == now.date():
            return False  # already refreshed today
    except (OSError, json.JSONDecodeError, ValueError):
        pass  # file absent or corrupt — proceed
    logger.info("AP inventory refresh triggered (00:00–00:20 UTC window).")
    try:
        subprocess.run(
            [sys.executable, str(script_path)],
            timeout=300,
            check=False,
            capture_output=True,
        )
    except Exception as exc:
        logger.warning("AP inventory refresh failed (ignored): %s", exc)
    return True


def build_idm(rows: list[dict], ts: int, derived_rules: list | None = None, ap_lookup: dict | None = None) -> dict:
    ts_str = str(ts)
    idm: dict = {}
    for row in rows:
        band = row["band"]
        if band not in SUPPORTED_BANDS:
            continue

        mac_raw = (row.get("ap_mac") or "").lower()
        own_ip = (row.get("ip") or "").strip()
        own_name = row.get("ap_name") or ""

        lookup = ap_lookup or {}
        devices = (lookup.get(mac_raw) or {}).get("devices") or {}

        # Instance name: Inventory MAC > Inventory serial > Inventory object_key
        # > the AP's own name. If none of these are available (Inventory miss
        # and no own name), drop the AP - never sent under any other fallback
        # identifier. An Inventory miss alone does NOT drop the AP.
        instance = build_instance_name(devices, own_name)
        if instance is None:
            continue

        if instance not in idm:
            entry: dict = {"in": instance, "dit": {ts_str: {"t": ts, "metricDataPointSet": []}}}

            # Instance metadata (display name / component name / IP / zone)
            # must be packed into a single "im" JSON string, not sent as flat
            # top-level keys - matches baicells-agent/tarana-gnmic-agent's
            # validated wire format. Flat keys are silently ignored by
            # InsightFinder for display name (component name/zone/IP happen
            # to still come through some other project-side mechanism, but
            # display name does not - pack all four to be safe and consistent).
            im_data: dict[str, str] = {}
            # Display name: always the AP's own name as reported, raw/uncleaned -
            # never falls back to the Inventory's name field.
            if own_name:
                im_data["idn"] = own_name
            cn = component_name_from_lookup(devices)
            if cn:
                im_data["cn"] = cn
            # IP: Inventory ip_address > the AP's own reported IP.
            ip = inv_field(devices, "ip_address") or own_ip
            if ip:
                im_data["i"] = ip
            # Zone: Inventory's subvenue only - omitted if not in Inventory.
            zone = inv_field(devices.get("meta") or {}, "subvenue")
            if zone:
                im_data["z"] = zone
            if im_data:
                entry["im"] = json.dumps(im_data)

            idm[instance] = entry

        mset = idm[instance]["dit"][ts_str]["metricDataPointSet"]

        # Channel utilization
        for metric, val in (
            (f"Channel Utilization ({band})", row["ChUtil_Busy"]),
        ):
            if val is not None:
                mset.append({"m": metric, "v": val})

        # 5GHz client metrics
        for metric, key in (
            ("Clients (5GHz)", "num_clients_5g"),
            ("RSSI Average (5GHz)", "rssi_avg_5g"),
            ("SNR Average (5GHz)", "snr_avg_5g"),
            ("% Clients RSSI < -74 dBm (5GHz)", "rssi_pct_below_74"),
            ("% Clients RSSI < -78 dBm (5GHz)", "rssi_pct_below_78"),
            ("% Clients RSSI < -80 dBm (5GHz)", "rssi_pct_below_80"),
            ("% Clients SNR < 15 dB (5GHz)", "snr_pct_below_15"),
            ("% Clients SNR < 18 dB (5GHz)", "snr_pct_below_18"),
            ("% Clients SNR < 20 dB (5GHz)", "snr_pct_below_20"),
        ):
            val = row.get(key)
            if val is not None:
                mset.append({"m": metric, "v": val})

        # Derived / compound metrics
        if derived_rules:
            flat = {dp["m"]: float(dp["v"]) for dp in mset if isinstance(dp.get("v"), (int, float))}
            tags = {"site": row.get("site", ""), "ap_name": row.get("ap_name", ""), "status": row.get("status", "")}
            for name, value in apply_derived_metrics(tags, flat, derived_rules):
                mset.append({"m": name, "v": value})

    return {k: v for k, v in idm.items() if v["dit"][ts_str]["metricDataPointSet"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Send UniFi AP 5GHz metrics to InsightFinder.")
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
    rssi_threshold = int(optional("MIN_CLIENTS_RSSI_THRESHOLD") or "10")
    snr_threshold = int(optional("MIN_CLIENTS_SNR_THRESHOLD") or "10")
    derived_rules = load_derived_metrics(optional("DERIVED_METRICS_SCRIPT"))

    # Device Inventory (Asset Registry) enrichment - leave both blank to disable.
    ap_inventory_base = optional("JIRAASSET_BASE")
    ap_inventory_key = optional("JIRAASSET_API_KEY")

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
        sampling_interval=int(optional("INSIGHTFINDER_SAMPLING_INTERVAL") or "5") * 60,
        create_project=True,
    )

    interval = config.sampling_interval
    logger.info(
        "Starting. RSSI threshold: %d clients, SNR threshold: %d clients.",
        rssi_threshold, snr_threshold,
    )

    lookup_path = Path(__file__).parent / "aplookup.json"
    not_found_path = Path(__file__).parent / "aplookupnotfound.json"
    lookup_script = Path(__file__).parent / "ap_inventory_lookup.py"
    ap_lookup = load_ap_lookup(lookup_path)
    ap_not_found = load_ap_not_found(not_found_path)

    if not (ap_inventory_base and ap_inventory_key):
        logger.warning("JIRAASSET_BASE/JIRAASSET_API_KEY not set - Inventory enrichment disabled.")

    logger.info("Fetching sites...")
    sites = list_sites(api_key)
    logger.info("Found %d site(s).", len(sites))

    with InsightFinder(config) as client:
        while True:
            ts = int(time.time() * 1000)

            # Refresh AP inventory once per day in the 00:00–00:20 UTC window.
            if maybe_refresh_ap_lookup(lookup_script, lookup_path):
                ap_lookup = load_ap_lookup(lookup_path)
                ap_not_found = load_ap_not_found(not_found_path)
                logger.info("Reloaded AP lookup (%d entries).", len(ap_lookup))

            all_rows = collect_ap_rows(
                api_key, sites=sites,
                rssi_threshold=rssi_threshold,
                snr_threshold=snr_threshold,
            )

            # Resolve any AP seen for the first time immediately, rather than
            # waiting for the once-daily inventory refresh window above.
            pending: set[str] = set()
            if ap_inventory_base and ap_inventory_key:
                pending = resolve_new_aps(
                    all_rows, ap_lookup, ap_not_found,
                    ap_inventory_base, ap_inventory_key, lookup_path, not_found_path,
                )

            if pending:
                # Never seen a completed lookup (API error, not a confirmed
                # miss) - exclude entirely rather than sending under its own
                # name; it'll be retried next cycle.
                before = len(all_rows)
                all_rows = [r for r in all_rows if (r.get("ap_mac") or "").lower() not in pending]
                logger.warning(
                    "Excluding %d row(s) for %d AP(s) still pending Inventory resolution - will retry next cycle",
                    before - len(all_rows), len(pending),
                )

            idm = build_idm(all_rows, ts, derived_rules=derived_rules, ap_lookup=ap_lookup)

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
