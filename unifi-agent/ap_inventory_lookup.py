#!/usr/bin/env python3
"""
Look up each UniFi AP in the AccessParks device inventory.

Identifier priority per AP: MAC → serial → IP → name.
Stops at the first identifier that returns a match.

Outputs:
  ap_lookup_matched.json   — APs found in the inventory (ap_key → {ap, identifier_used, devices})
  ap_lookup_not_found.json — APs with no match found
"""

import datetime
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from get_metrics import fetch_site_devices_legacy, list_sites, load_env

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

def lookup_device(identifier: str, base_url: str, api_key: str) -> list[dict] | None:
    """GET /devices/{identifier}. Returns list (empty = not found) or None on request error."""
    url = f"{base_url}/devices/{urllib.parse.quote(identifier, safe='')}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "X-API-Key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        logger.warning("HTTP %d looking up %r", e.code, identifier)
        return None
    except urllib.error.URLError as e:
        logger.warning("Request failed for %r: %s", identifier, e)
        return None


def find_in_inventory(ap: dict, base_url: str, api_key: str) -> tuple[str | None, list[dict]]:
    """Try identifiers in priority order: MAC → serial → IP → name."""
    for ident in (ap["mac"], ap["serial"], ap["ip"], ap["name"]):
        if not ident:
            continue
        result = lookup_device(ident, base_url, api_key)
        if result:
            return ident, result
        time.sleep(0.05)
    return None, []


def collect_all_aps(api_key: str) -> list[dict]:
    sites = list_sites(api_key)
    logger.info("Found %d site(s).", len(sites))

    by_host: dict[str, list[dict]] = {}
    for s in sites:
        by_host.setdefault(s["hostId"], []).append(s)

    aps: list[dict] = []
    done, total = 0, len(sites)
    for host_id, host_sites in by_host.items():
        for site in host_sites:
            done += 1
            logger.info("[%d/%d] Fetching devices from %s...", done, total, site["siteName"])
            devices = fetch_site_devices_legacy(host_id, site["siteSlug"], api_key, retries=2)
            if not devices:
                continue
            ap_devices = [d for d in devices if d.get("type") == "uap"]
            if not ap_devices:
                ap_devices = [d for d in devices if "radio_table" in d or "radio_table_stats" in d]
            for ap in ap_devices:
                aps.append({
                    "site": site["siteName"],
                    "name": ap.get("name") or "",
                    "ip": ap.get("ip") or "",
                    "mac": ap.get("mac") or "",
                    "serial": ap.get("serial") or "",
                })
            time.sleep(0.1)
    return aps


def main() -> None:
    env_path = Path(__file__).parent / ".env"
    env = load_env(env_path)

    def require(var: str) -> str:
        val = env.get(var) or os.environ.get(var)
        if not val:
            raise SystemExit(f"{var} not set in .env or environment.")
        return val

    api_key = require("UNIFI_API_KEY")
    ap_base_url = require("JIRAASSET_BASE")
    ap_api_key = require("JIRAASSET_API_KEY")

    matched_path = Path(__file__).parent / "aplookup.json"
    not_found_path = Path(__file__).parent / "aplookupnotfound.json"

    # Load existing data — only update entries, never delete.
    matched: dict = {}
    not_found: dict = {}
    for path, target in ((matched_path, matched), (not_found_path, not_found)):
        if path.exists():
            try:
                target.update(json.loads(path.read_text()))
            except (json.JSONDecodeError, OSError):
                pass

    logger.info("Collecting APs from UniFi...")
    aps = collect_all_aps(api_key)
    logger.info("Collected %d AP(s) total.", len(aps))

    for i, ap in enumerate(aps, 1):
        mac = (ap["mac"] or "").lower()
        ap_key = mac or ap["ip"] or ap["name"]
        logger.info(
            "[%d/%d] mac=%s  name=%s  serial=%s  ip=%s",
            i, len(aps), mac, ap["name"], ap["serial"], ap["ip"],
        )

        ident_used, devices = find_in_inventory(ap, ap_base_url, ap_api_key)
        if devices:
            logger.info("  -> matched via %r", ident_used)
            matched[ap_key] = {
                "ap": ap,
                "identifier_used": ident_used,
                "devices": devices,
            }
        else:
            logger.info("  -> not found")
            not_found[ap_key] = {"ap": ap}

    matched["lastmodifiedtimedata"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    matched_path.write_text(json.dumps(matched, indent=2))
    not_found_path.write_text(json.dumps(not_found, indent=2))

    logger.info(
        "Done. Matched: %d | Not found: %d | Total: %d",
        len(matched), len(not_found), len(aps),
    )


if __name__ == "__main__":
    main()
