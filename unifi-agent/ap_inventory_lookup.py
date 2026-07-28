#!/usr/bin/env python3
"""
Look up each UniFi AP in the AccessParks device inventory.

Identifier priority per AP: MAC → serial → name (same convention as the other
InsightFinder agents - see devicelookup.go in positron-agent/baicells-agent).
Stops at the first identifier that returns a match. IP is deliberately not an
identifier candidate - it's not stable enough to key a device identity on.

Outputs:
  aplookup.json          — APs found in the inventory (ap_key → {ap, identifier_used, devices})
  aplookupnotfound.json  — APs with no match found

resolve_ap() is also imported by send_metrics.py to look up an AP the moment
it's first seen, rather than waiting for this script's once-daily batch run.
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

def lookup_device(identifier: str, base_url: str, api_key: str) -> dict | None:
    """GET /devices/{identifier}. Returns the device record (empty dict = not found) or None on request error."""
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
            return {}
        logger.warning("HTTP %d looking up %r", e.code, identifier)
        return None
    except urllib.error.URLError as e:
        logger.warning("Request failed for %r: %s", identifier, e)
        return None


def find_in_inventory(ap: dict, base_url: str, api_key: str) -> tuple[str | None, dict, bool]:
    """Try identifiers in priority order: MAC → serial → name.

    Returns:
      (ident, devices, False)  — matched
      (None,  {},      False)  — not found (all returned 404)
      (None,  {},      True)   — API/network error; caller should preserve
                                  whatever entry already exists rather than
                                  treating this as a confirmed miss
    """
    for ident in (ap.get("mac"), ap.get("serial"), ap.get("name")):
        if not ident:
            continue
        result = lookup_device(ident, base_url, api_key)
        if result is None:
            return None, {}, True   # error — stop, preserve existing data
        if result:
            return ident, result, False
        time.sleep(0.05)
    return None, {}, False          # all identifiers tried, all returned 404


def ap_key_for(ap: dict) -> str:
    return (ap.get("mac") or "").lower() or ap.get("ip") or ap.get("name") or ""


def resolve_ap(ap: dict, base_url: str, api_key: str) -> tuple[str, dict | None, bool]:
    """Look up one AP. Returns (ap_key, matched_entry, had_error).
    matched_entry is None when the AP has no Inventory match (caller should
    record it as not-found) - UNLESS had_error is True, in which case this was
    an API/network error, not a confirmed miss, and the caller must leave any
    existing entry for this AP untouched rather than evicting it."""
    ap_key = ap_key_for(ap)
    ident_used, devices, had_error = find_in_inventory(ap, base_url, api_key)
    if devices:
        return ap_key, {"ap": ap, "identifier_used": ident_used, "devices": devices}, False
    return ap_key, None, had_error


def atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


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

    # Safety gate 1: UniFi returned nothing — its API may be down; don't touch
    # the cache files at all (an empty aps list would otherwise leave the loop
    # below a no-op while still stamping lastmodifiedtimedata as if a real
    # refresh had happened).
    if not aps:
        logger.warning("No APs collected from UniFi — JSON files not updated")
        return

    error_count = 0
    update_count = 0
    for i, ap in enumerate(aps, 1):
        logger.info(
            "[%d/%d] mac=%s  name=%s  serial=%s  ip=%s",
            i, len(aps), (ap["mac"] or "").lower(), ap["name"], ap["serial"], ap["ip"],
        )

        ap_key, matched_entry, had_error = resolve_ap(ap, ap_base_url, ap_api_key)
        if had_error:
            error_count += 1
            logger.warning("  -> API error — preserving existing entry (if any)")
            continue

        update_count += 1
        if matched_entry:
            logger.info("  -> matched via %r", matched_entry["identifier_used"])
            matched[ap_key] = matched_entry
            not_found.pop(ap_key, None)
        else:
            logger.info("  -> not found")
            not_found[ap_key] = {"ap": ap}
            matched.pop(ap_key, None)

    # Safety gate 2: every single lookup errored out — the inventory server is
    # likely down. Don't overwrite the cache with an unchanged/stale snapshot
    # stamped as freshly refreshed.
    if update_count == 0:
        logger.error(
            "All %d inventory lookups returned API errors — inventory server may be down. "
            "JSON files NOT overwritten.", error_count,
        )
        return

    if error_count:
        logger.warning(
            "%d/%d AP(s) had API errors and were skipped — their existing entries are preserved",
            error_count, len(aps),
        )

    matched["lastmodifiedtimedata"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    atomic_write_json(matched_path, matched)
    atomic_write_json(not_found_path, not_found)

    matched_count = sum(1 for k in matched if k != "lastmodifiedtimedata")
    logger.info(
        "Done. Matched: %d | Not found: %d | Errors (skipped): %d | Total: %d",
        matched_count, len(not_found), error_count, len(aps),
    )


if __name__ == "__main__":
    main()
