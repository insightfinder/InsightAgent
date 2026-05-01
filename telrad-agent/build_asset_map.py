#!/usr/bin/env python3
"""
Build asset_map.json — maps BreezeVIEW eNB device IDs to Jira asset names.

Matching strategy (in priority order):
  1. DeviceName numeric suffix  — Jira DeviceName="eNodeB200" → device_id "200"
                                    Stable even when management IP changes.
  2. management_ip              — for assets whose DeviceName carries no embedded ID.

Usage:
  python3 build_asset_map.py            # build and write asset_map.json
  python3 build_asset_map.py --print    # also pretty-print the result
"""

import argparse
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from get_metrics import _cfg, get_device_ip_map, get_device_name_map, load_env
from jira_assets import ENB_NAME_RE, discover_workspace_id, fetch_assets_by_ips

ASSET_MAP_FILE = "asset_map.json"
MAP_STALE_DAYS = 7


def map_age_days(asset_map: dict) -> int | None:
    """Return age of asset_map in whole days, or None if timestamp is absent/invalid."""
    generated_at = asset_map.get("generated_at", "")
    if not generated_at:
        return None
    try:
        return (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        ).days
    except ValueError:
        return None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)


def _resolve_map(device_ip_map: dict[str, str], assets: list[dict], device_name_map: dict[str, str]) -> dict[str, str]:
    """Return {device_id: label} using two-tier Jira matching with BreezeVIEW name fallback.

    Tier 1: asset.device_id_hint == device_id (numeric suffix from Jira DeviceName)
    Tier 2: asset.ip == device_ip (management IP fallback)
    Tier 3: config/Device/General/Name from BreezeVIEW (e.g. 'DeathValley-Oasis')
    """
    by_hint: dict[str, list[dict]] = {}
    by_ip: dict[str, list[dict]] = {}
    for a in assets:
        if a["device_id_hint"]:
            by_hint.setdefault(a["device_id_hint"], []).append(a)
        if a["ip"]:
            by_ip.setdefault(a["ip"], []).append(a)

    def pick_candidate(candidates: list[dict]) -> dict:
        if len(candidates) == 1:
            return candidates[0]
        enb_ones = [c for c in candidates if ENB_NAME_RE.search(c["label"])]
        chosen = enb_ones[0] if enb_ones else candidates[0]
        labels = [c["label"] for c in candidates]
        logger.warning(f"Multiple Jira assets matched (picking '{chosen['label']}'): {labels}")
        return chosen

    result: dict[str, str] = {}
    for device_id, ip in device_ip_map.items():
        if device_id in by_hint:
            candidates = by_hint[device_id]
            chosen = pick_candidate(candidates)
            label = chosen["label"]
            result[device_id] = label
            asset_ip = chosen["ip"]
            if ip and asset_ip and ip != asset_ip:
                logger.warning(f"  eNB {device_id} → {label}  [matched by DeviceName suffix '{device_id}'] IP MISMATCH: BreezeVIEW={ip}, Jira={asset_ip}")
            else:
                logger.info(f"  eNB {device_id} → {label}  [matched by DeviceName suffix '{device_id}', IP verified: {ip or 'N/A'}]")
        elif ip in by_ip:
            label = pick_candidate(by_ip[ip])["label"]
            result[device_id] = label
            logger.info(f"  eNB {device_id} ({ip}) → {label}  [matched by IP]")
        else:
            fallback = device_name_map.get(device_id) or device_id
            result[device_id] = fallback
            logger.warning(f"  eNB {device_id} ({ip}): no Jira match — using BreezeVIEW name '{fallback}' as instance name")

    return result


def build(env: dict | None = None) -> dict:
    """Build and write asset_map.json; return the map dict.

    Importable by send_metrics.py for automatic bootstrap when the file is absent.
    """
    if env is None:
        env = load_env()

    jira_url = _cfg(env, "ACCESSPARKS_JIRA_URL")
    jira_user = _cfg(env, "ACCESSPARKS_JIRA_USERNAME")
    jira_token = _cfg(env, "ACCESSPARKS_JIRA_API_TOKEN")
    bv_url = _cfg(env, "ACCESSPARKS_TELRAD_URL").rstrip("/")
    bv_user = _cfg(env, "ACCESSPARKS_TELRAD_USERNAME")
    bv_pw = _cfg(env, "ACCESSPARKS_TELRAD_PASSWORD")

    missing = [k for k, v in [("ACCESSPARKS_JIRA_URL", jira_url), ("ACCESSPARKS_JIRA_USERNAME", jira_user), ("ACCESSPARKS_JIRA_API_TOKEN", jira_token)] if not v]
    if missing:
        raise ValueError(f"Missing Jira config: {', '.join(missing)} — add to .env")

    # BreezeVIEW device list, name map, and Jira workspace ID are independent — fetch in parallel
    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_bv = pool.submit(get_device_ip_map, bv_url, bv_user, bv_pw, 15)
        fut_names = pool.submit(get_device_name_map, bv_url, bv_user, bv_pw, 15)
        fut_ws = pool.submit(discover_workspace_id, jira_url, jira_user, jira_token)
        device_ip_map = fut_bv.result()
        device_name_map = fut_names.result()
        workspace_id = fut_ws.result()

    ips = [ip for ip in device_ip_map.values() if ip]
    logger.info(f"Querying Jira Assets for {len(ips)} eNB IP(s)...")
    assets = fetch_assets_by_ips(workspace_id, jira_user, jira_token, ips)

    by_device_id = _resolve_map(device_ip_map, assets, device_name_map)

    asset_map = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "by_device_id": by_device_id,
    }

    tmp = ASSET_MAP_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(asset_map, f, indent=2)
    os.replace(tmp, ASSET_MAP_FILE)

    logger.info(f"Mapped {len(by_device_id)}/{len(device_ip_map)} eNBs — wrote {ASSET_MAP_FILE}")
    return asset_map


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Jira → BreezeVIEW eNB asset name map")
    parser.add_argument("--print", dest="do_print", action="store_true", help="Print asset_map.json after building")
    args = parser.parse_args()

    try:
        asset_map = build()
    except Exception as e:
        logger.error(f"Failed to build asset map: {e}")
        sys.exit(1)

    if args.do_print:
        print(json.dumps(asset_map, indent=2))


if __name__ == "__main__":
    main()
