#!/usr/bin/env python3
"""Fetch UniFi AP 5GHz metrics and send to InsightFinder."""

import argparse
import datetime
import importlib.util
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from get_metrics import SUPPORTED_BANDS, collect_ap_rows, list_sites, load_env
from insightfinder import Config, InsightFinder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

_BAD_INSTANCE_CHARS = str.maketrans({c: "-" for c in " ,_@#:"})
_MULTI_DASH = re.compile(r"-{2,}")


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


def component_name_from_lookup(mac: str, ap_lookup: dict) -> str:
    """Return 'Manufacturer-DeviceClass' from aplookup.json, or empty string."""
    entry = ap_lookup.get(mac) or {}
    model = (entry.get("devices") or {}).get("model") or {}
    manufacturer = (model.get("manufacturer") or "").strip()
    device_class = (model.get("device_class") or "").strip()
    if manufacturer and device_class:
        return f"{manufacturer}-{device_class}"
    return manufacturer or device_class


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


def sanitize_name(name: str) -> str:
    """Replace banned chars (space , _ @ # :) with -, collapsing runs."""
    return _MULTI_DASH.sub("-", (name or "unknown").translate(_BAD_INSTANCE_CHARS)).strip("-") or "unknown"


def build_idm(rows: list[dict], ts: int, derived_rules: list | None = None, ap_lookup: dict | None = None) -> dict:
    ts_str = str(ts)
    idm: dict = {}
    for row in rows:
        band = row["band"]
        if band not in SUPPORTED_BANDS:
            continue

        mac_raw = (row.get("ap_mac") or "").lower()
        ip = (row.get("ip") or "").strip()
        site = row.get("site") or ""

        # Only send metrics for APs present in the inventory lookup.
        lookup = ap_lookup or {}
        if not mac_raw or mac_raw not in lookup:
            continue

        instance = sanitize_name(mac_raw)

        if instance not in idm:
            entry: dict = {"in": instance, "dit": {ts_str: {"t": ts, "metricDataPointSet": []}}}
            cn = component_name_from_lookup(mac_raw, lookup)
            if not cn and site:
                cn = sanitize_name(site)
            if cn:
                entry["cn"] = cn
            if ip:
                entry["i"] = ip
            try:
                zone = lookup[mac_raw]["devices"]["meta"]["subvenue"]
                if zone:
                    entry["z"] = zone
            except (KeyError, TypeError):
                pass
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
            tags = {"site": site, "ap_name": row.get("ap_name", ""), "status": row.get("status", "")}
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
    lookup_script = Path(__file__).parent / "ap_inventory_lookup.py"
    ap_lookup = load_ap_lookup(lookup_path)

    logger.info("Fetching sites...")
    sites = list_sites(api_key)
    logger.info("Found %d site(s).", len(sites))

    with InsightFinder(config) as client:
        while True:
            ts = int(time.time() * 1000)

            # Refresh AP inventory once per day in the 00:00–00:20 UTC window.
            if maybe_refresh_ap_lookup(lookup_script, lookup_path):
                ap_lookup = load_ap_lookup(lookup_path)
                logger.info("Reloaded AP lookup (%d entries).", len(ap_lookup))

            all_rows = collect_ap_rows(
                api_key, sites=sites,
                rssi_threshold=rssi_threshold,
                snr_threshold=snr_threshold,
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
