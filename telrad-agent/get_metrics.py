#!/usr/bin/env python3
"""
Fetch signal metrics (dBm) for all BreezeVIEW-managed eNBs via the REST NBI.

Metrics collected (eNB-side, via REST):
  - SasKpis: cell-level uplink RMS power for Cell0 and Cell1 (dBm)
  - UeKPIsList: per-UE UlRSSI (dBm), UlCINR (dB), DlBLER/UlBLER, DlMCS/UlMCS, Distance, CellID, RNTI, TEID

CPE-side metrics (RSRP0/1, SINR0/1, RSRQ) require the BreezeVIEW CLI kpi-snapshot SSH flow
and are NOT available via REST. See docs/BreezeVIEW - How to Get UE(s) KPIs via BreezeVIEW CLI.md.

Usage:
  python3 get_metrics.py
  python3 get_metrics.py --output metrics.json
  python3 get_metrics.py --device 20
  python3 get_metrics.py --timeout 30 --json-only
"""

import argparse
import base64
import json
import logging
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)


NS_ENB_PM = "http://LTE_COMPACT.com/LTE_ENB_PM"
NS_ENB_PM_UE = "http://LTE_COMPACT.com/LTE_ENB_PM_UE"


def load_env(path=".env"):
    env = {}
    if not os.path.exists(path):
        return env
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            val = val.strip()
            if val and val[0] in ('"', "'"):
                # Quoted value — take content as-is, no comment stripping
                q = val[0]
                end = val.rfind(q, 1)
                val = val[1:end] if end > 0 else val[1:]
            else:
                val = val.split("#")[0].strip()
            env[key.strip()] = val
    return env


def _cfg(env: dict, key: str) -> str:
    return os.environ.get(key) or env.get(key, "")


def _localname(el) -> str:
    return el.tag.split("}")[-1] if "}" in el.tag else el.tag


def make_request(url, username, password, timeout):
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {creds}"})
    return urllib.request.urlopen(req, timeout=timeout)


def get_device_ip_map(base_url, username, password, timeout) -> dict:
    """Return {device_id: ip_address} for all unique-IP eNBs."""
    url = f"{base_url}/api/running/devices/device?select=name;address"
    resp = make_request(url, username, password, timeout)
    root = ET.fromstring(resp.read())
    ns = {"ncs": "http://tail-f.com/ns/ncs"}
    seen_ips: set = set()
    result: dict = {}
    for device in root.findall(".//ncs:device", ns):
        name_el = device.find("ncs:name", ns)
        addr_el = device.find("ncs:address", ns)
        name = name_el.text if name_el is not None else None
        address = addr_el.text if addr_el is not None else None
        if not name:
            continue
        if address and address in seen_ips:
            continue
        if address:
            seen_ips.add(address)
        result[name] = address or ""
    return result


def get_device_name_map(base_url, username, password, timeout) -> dict:
    """Return {device_id: display_name} from config/Device/General/Name."""
    url = f"{base_url}/api/running/devices/device?select=name;config/Device/General/Name"
    resp = make_request(url, username, password, timeout)
    root = ET.fromstring(resp.read())
    result: dict = {}

    for device in root:
        if _localname(device) != "device":
            continue
        name_el = next((c for c in device if _localname(c) == "name"), None)
        if name_el is None or not name_el.text:
            continue
        display = ""
        cursor = next((c for c in device if _localname(c) == "config"), None)
        if cursor is not None:
            for path_tag in ("Device", "General", "Name"):
                cursor = next((c for c in cursor if _localname(c) == path_tag), None)
                if cursor is None:
                    break
            if cursor is not None and cursor.text:
                display = cursor.text.strip()
        result[name_el.text] = display
    return result


def get_device_ids(base_url, username, password, timeout) -> list:
    return list(get_device_ip_map(base_url, username, password, timeout).keys())


def get_device_metrics(base_url, device_id, username, password, timeout):
    url = (
        f"{base_url}/api/operational/devices/device/{device_id}"
        "/live-status?select=UeKPIsList;SasKpis"
    )
    try:
        resp = make_request(url, username, password, timeout)
        xml_bytes = resp.read()
    except urllib.error.HTTPError as e:
        return {"device_id": device_id, "status": "error", "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"device_id": device_id, "status": "error", "error": str(e)}

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        return {"device_id": device_id, "status": "error", "error": f"XML parse error: {e}"}

    # Check for RPC fault (unreachable device)
    fault = root.find(".//{http://tail-f.com/ns/rest}error")
    if fault is None:
        fault = root.find(".//error")
    if fault is not None:
        msg = fault.findtext("message") or fault.findtext("info") or ET.tostring(fault, encoding="unicode")
        return {"device_id": device_id, "status": "error", "error": msg.strip()}

    result = {"device_id": device_id, "status": "ok"}

    # Cell-level metrics
    sas = root.find(f"{{{NS_ENB_PM}}}SasKpis")
    if sas is not None:
        def sas_int(tag):
            el = sas.find(f"{{{NS_ENB_PM}}}{tag}")
            return int(el.text) if el is not None and el.text else None

        result["cell_metrics"] = {
            "cell0_ul_rms_power_dbm": sas_int("TotalUlRmsPowerOverBWCell0"),
            "cell1_ul_rms_power_dbm": sas_int("TotalUlRmsPowerOverBWCell1"),
        }

    # Per-UE metrics
    ues = []
    for ue_el in root.findall(f"{{{NS_ENB_PM_UE}}}UeKPIsList"):
        def ue_val(tag, cast=int):
            el = ue_el.find(f"{{{NS_ENB_PM_UE}}}{tag}")
            if el is None or not el.text:
                return None
            try:
                return cast(el.text)
            except (ValueError, TypeError):
                return el.text

        ues.append({
            "enb_id": device_id,
            "teid": ue_val("TEID", str),
            "rnti": ue_val("RNTI"),
            "cell_id": ue_val("CellID"),
            "ul_rssi_dbm": ue_val("UlRSSI"),
            "ul_cinr_db": ue_val("UlCINR"),
            "dl_bler_pct": ue_val("DlBLER"),
            "ul_bler_pct": ue_val("UlBLER"),
            "dl_mcs": ue_val("DlMCS"),
            "ul_mcs": ue_val("UlMCS"),
            "distance_m": ue_val("Distance"),
        })

    result["ues"] = ues
    return result


def collect_metrics(base_url, username, password, timeout, device_id=None):
    """Fetch metrics for all (or one) eNB(s) and return (timestamp_ms, device_results).

    Returns (timestamp_ms, list[device_result])."""
    if device_id is not None:
        device_ids = [device_id]
        name_map = {}
    else:
        logger.debug("Enumerating devices...")
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_ids = pool.submit(get_device_ip_map, base_url, username, password, timeout)
            fut_names = pool.submit(get_device_name_map, base_url, username, password, timeout)
            device_ids = list(fut_ids.result().keys())
            try:
                name_map = fut_names.result()
            except Exception:
                name_map = {}
        logger.debug(f"Found {len(device_ids)} eNB device(s): {', '.join(device_ids)}")

    def fetch(did):
        logger.debug(f"Fetching metrics for eNB {did}...")
        result = get_device_metrics(base_url, did, username, password, timeout)
        result["device_name"] = name_map.get(did, "")
        if result["status"] == "ok":
            logger.debug(f"eNB {did}: ok ({len(result.get('ues', []))} UEs attached)")
        else:
            logger.debug(f"eNB {did}: error — {result['error']}")
        return result

    with ThreadPoolExecutor(max_workers=min(len(device_ids), 8)) as pool:
        results = list(pool.map(fetch, device_ids))

    ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return ts_ms, results


def print_summary(devices, all_ues=False):
    for d in devices:
        name = d.get("device_name") or ""
        label = f"{d['device_id']}  ({name})" if name else d['device_id']
        if d["status"] == "error":
            print(f"[eNB {label}]  UNREACHABLE — {d['error']}")
            continue

        cm = d.get("cell_metrics", {})
        ues = d.get("ues", [])
        cell0 = cm.get("cell0_ul_rms_power_dbm")
        cell1 = cm.get("cell1_ul_rms_power_dbm")
        print(
            f"[eNB {label}]  "
            f"Cell0 UL RMS: {cell0} dBm  Cell1 UL RMS: {cell1} dBm  "
            f"UEs attached: {len(ues)}"
        )
        rssi_sorted = sorted(
            (u for u in ues if u.get("ul_rssi_dbm") is not None),
            key=lambda u: u["ul_rssi_dbm"],
        )
        shown = rssi_sorted if all_ues else rssi_sorted[:5]
        for u in shown:
            print(
                f"    TEID {u['teid']:>6}  RNTI {u['rnti']:>5}  Cell {u['cell_id']}"
                f"  UlRSSI {u['ul_rssi_dbm']:>4} dBm"
                f"  UlCINR {u['ul_cinr_db']:>3} dB"
            )
        if not all_ues and len(rssi_sorted) > 5:
            print(f"    ... and {len(ues) - 5} more UEs")


def main():
    parser = argparse.ArgumentParser(description="Fetch BreezeVIEW eNB signal metrics via REST NBI")
    parser.add_argument("--output", metavar="FILE", help="Write JSON to file")
    parser.add_argument("--device", metavar="ID", help="Query a single device ID only")
    parser.add_argument("--timeout", type=int, default=15, metavar="SEC", help="HTTP timeout in seconds (default: 15)")
    parser.add_argument("--json-only", action="store_true", help="Print JSON to stdout instead of human-readable summary")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("-a", "--all-ues", action="store_true", help="Print all UEs, not just top 5")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    env = load_env()
    base_url = _cfg(env, "ACCESSPARKS_TELRAD_URL").rstrip("/")
    username = _cfg(env, "ACCESSPARKS_TELRAD_USERNAME")
    password = _cfg(env, "ACCESSPARKS_TELRAD_PASSWORD")

    if not base_url or not username or not password:
        logger.error("set ACCESSPARKS_TELRAD_URL, ACCESSPARKS_TELRAD_USERNAME, ACCESSPARKS_TELRAD_PASSWORD in .env")
        sys.exit(1)

    try:
        ts_ms, results = collect_metrics(
            base_url, username, password, args.timeout,
            device_id=args.device,
        )
    except Exception as e:
        logger.error(str(e))
        sys.exit(1)

    payload = {
        "timestamp": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "devices": results,
    }
    json_str = json.dumps(payload, indent=2)

    if args.json_only:
        print(json_str)
    else:
        print_summary(results, all_ues=args.all_ues)
        if args.output:
            with open(args.output, "w") as f:
                f.write(json_str)
            print(f"\nJSON written to {args.output}")


if __name__ == "__main__":
    main()
