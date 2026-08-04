#!/usr/bin/env python3
"""
Look up each UISP device in the AccessParks device inventory.

Identifier priority per device: MAC -> serial -> name (same convention as the
other InsightFinder agents - see devicelookup.go in positron-agent/baicells-agent,
device_inventory_lookup.py in zabbix-ap). Stops at the first identifier that
returns a match. IP is deliberately not an identifier candidate - it's not
stable enough to key a device identity on.

Outputs:
  devicelookup.json          - devices found in the inventory (device_key -> {device, identifier_used, devices})
  devicelookupnotfound.json  - devices with no match found

resolve_device() is also imported by send_metrics.py to look up a device the
moment it's first seen, rather than waiting for this script's once-daily
batch run.
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

from dotenv import load_dotenv

from get_metrics import get_devices, extract_device_metrics

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


def find_in_inventory(device: dict, base_url: str, api_key: str) -> tuple[str | None, dict, bool]:
    """Try identifiers in priority order: MAC -> serial -> name.

    Returns:
      (ident, devices, False)  - matched
      (None,  {},      False)  - not found (all returned 404)
      (None,  {},      True)   - API/network error; caller should preserve
                                  whatever entry already exists rather than
                                  treating this as a confirmed miss
    """
    for ident in (device.get("mac"), device.get("serialNumber"), device.get("name")):
        if not ident:
            continue
        result = lookup_device(ident, base_url, api_key)
        if result is None:
            return None, {}, True   # error - stop, preserve existing data
        if result:
            return ident, result, False
        time.sleep(0.05)
    return None, {}, False          # all identifiers tried, all returned 404


def device_key_for(device: dict) -> str:
    return (device.get("mac") or "").lower() or device.get("serialNumber") or device.get("name") or ""


def resolve_device(device: dict, base_url: str, api_key: str) -> tuple[str, dict | None, bool]:
    """Look up one device. Returns (device_key, matched_entry, had_error).
    matched_entry is None when the device has no Inventory match (caller
    should record it as not-found) - UNLESS had_error is True, in which case
    this was an API/network error, not a confirmed miss, and the caller must
    leave any existing entry for this device untouched rather than evicting
    it."""
    device_key = device_key_for(device)
    ident_used, devices, had_error = find_in_inventory(device, base_url, api_key)
    if devices:
        return device_key, {"device": device, "identifier_used": ident_used, "devices": devices}, False
    return device_key, None, had_error


def atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def collect_all_devices(api_token: str) -> list[dict]:
    """Fetch every device from UISP (regardless of status) and extract just
    the identifiers needed for inventory lookup."""
    raw_devices = get_devices(api_token)
    devices: list[dict] = []
    for raw in raw_devices:
        metrics = extract_device_metrics(raw)
        devices.append({
            "name": metrics.get("name") or "",
            "mac": (metrics.get("mac") or "").lower(),
            "serialNumber": metrics.get("serialNumber") or "",
            "ip": metrics.get("ipAddress") or "",
        })
    return devices


def main() -> None:
    script_dir = Path(__file__).parent
    load_dotenv(script_dir / ".env")

    def require(var: str) -> str:
        val = os.environ.get(var)
        if not val:
            raise SystemExit(f"{var} not set in .env or environment.")
        return val

    api_token = os.environ.get("API_TOKEN") or os.environ.get("UISP_API_TOKEN")
    if not api_token:
        raise SystemExit("API_TOKEN or UISP_API_TOKEN not set in .env or environment.")
    inv_base_url = require("JIRAASSET_BASE")
    inv_api_key = require("JIRAASSET_API_KEY")

    matched_path = script_dir / "devicelookup.json"
    not_found_path = script_dir / "devicelookupnotfound.json"

    # Load existing data - only update entries, never delete.
    matched: dict = {}
    not_found: dict = {}
    for path, target in ((matched_path, matched), (not_found_path, not_found)):
        if path.exists():
            try:
                target.update(json.loads(path.read_text()))
            except (json.JSONDecodeError, OSError):
                pass

    logger.info("Collecting devices from UISP...")
    devices = collect_all_devices(api_token)
    logger.info("Collected %d device(s) total.", len(devices))

    # Safety gate 1: UISP returned nothing - its API may be down; don't touch
    # the cache files at all.
    if not devices:
        logger.warning("No devices collected from UISP - JSON files not updated")
        return

    error_count = 0
    update_count = 0
    for i, device in enumerate(devices, 1):
        logger.info(
            "[%d/%d] mac=%s  name=%s  serial=%s",
            i, len(devices), device["mac"], device["name"], device["serialNumber"],
        )

        device_key, matched_entry, had_error = resolve_device(device, inv_base_url, inv_api_key)
        if had_error:
            error_count += 1
            logger.warning("  -> API error - preserving existing entry (if any)")
            continue

        update_count += 1
        if matched_entry:
            logger.info("  -> matched via %r", matched_entry["identifier_used"])
            matched[device_key] = matched_entry
            not_found.pop(device_key, None)
        else:
            logger.info("  -> not found")
            not_found[device_key] = {"device": device}
            matched.pop(device_key, None)

    # Safety gate 2: every single lookup errored out - the inventory server is
    # likely down. Don't overwrite the cache with an unchanged/stale snapshot
    # stamped as freshly refreshed.
    if update_count == 0:
        logger.error(
            "All %d inventory lookups returned API errors - inventory server may be down. "
            "JSON files NOT overwritten.", error_count,
        )
        return

    if error_count:
        logger.warning(
            "%d/%d device(s) had API errors and were skipped - their existing entries are preserved",
            error_count, len(devices),
        )

    matched["lastmodifiedtimedata"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    atomic_write_json(matched_path, matched)
    atomic_write_json(not_found_path, not_found)

    matched_count = sum(1 for k in matched if k != "lastmodifiedtimedata")
    logger.info(
        "Done. Matched: %d | Not found: %d | Errors (skipped): %d | Total: %d",
        matched_count, len(not_found), error_count, len(devices),
    )


if __name__ == "__main__":
    main()
