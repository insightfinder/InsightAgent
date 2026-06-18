#!/usr/bin/env python3
"""
Look up each Zabbix host in the AccessParks device inventory.

Identifier priority per host: jira_device_key tag → zabbix_host_id → ip_address.

Reads all conf.d/*.ini files to collect host_groups, connects to each Zabbix instance,
then queries the inventory API for every unique host found — in parallel.

Outputs (same directory as this script):
  devicelookup.json         — hosts found (zabbix_host_id → {host, identifier_used, device})
  devicelookupnotfound.json — hosts with no match (zabbix_host_id → {host})

Safety guarantees:
  - Files are never overwritten if Zabbix returns no hosts (Zabbix down).
  - Hosts that hit an API error are skipped — their existing entry is preserved.
  - Files are never overwritten if every single lookup failed (inventory server down).
  - Writes are atomic (temp file + rename) so a crash mid-write never corrupts the file.

Usage:
  python device_inventory_lookup.py [--workers N]   default: 20
"""

import argparse
import configparser
import datetime
import glob
import json
import logging
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from pyzabbix import ZabbixAPI

requests.packages.urllib3.disable_warnings()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

INVENTORY_BASE_URL = "http://54.234.90.98"
INVENTORY_API_KEY = ""

# Shared session — connection pooling, keep-alive, reused across all threads
_session = requests.Session()
_session.headers.update({"Accept": "application/json", "X-API-Key": INVENTORY_API_KEY})
_session.verify = False


def lookup_device(identifier: str):
    """GET /devices/{identifier}.
    Returns:
      list of dicts  — success (empty list = 404 / not found)
      None           — network/server error (caller should treat as API down)
    """
    url = "{}/devices/{}".format(INVENTORY_BASE_URL, urllib.parse.quote(str(identifier), safe=""))
    try:
        resp = _session.get(url, timeout=10)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return [data] if isinstance(data, dict) else data
    except requests.HTTPError as e:
        logger.warning("HTTP %d looking up %r", e.response.status_code, identifier)
        return None
    except requests.RequestException as e:
        logger.warning("Request failed for %r: %s", identifier, e)
        return None


def find_in_inventory(host: dict):
    """Try identifiers in priority order: jira_device_key → zabbix_host_id → ip.

    jira_device_key is a Zabbix host tag whose value is the inventory object_key (e.g. IHS-23344).

    Returns:
      (ident, device_dict, False)  — matched
      (None,  None,        False)  — not found (all returned 404)
      (None,  None,        True)   — API/network error; existing entry should be preserved
    """
    for ident in (host.get("jira_key"), host["hostid"], host["ip"]):
        if not ident:
            continue
        result = lookup_device(ident)
        if result is None:
            return None, None, True   # server error — stop, preserve existing data
        if result:
            return ident, result[0], False
    return None, None, False          # all identifiers tried, all returned 404


def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically: write to .tmp then rename so the original is never left half-written."""
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def collect_hosts_from_config(config_file: str) -> list:
    """Parse a config.ini, connect to Zabbix, and return all hosts in the configured host_groups."""
    config_parser = configparser.ConfigParser(interpolation=None)
    config_parser.read(config_file)

    try:
        zabbix_url = config_parser.get("zabbix", "url")
        zabbix_user = config_parser.get("zabbix", "user")
        zabbix_password = config_parser.get("zabbix", "password")
        host_groups_raw = config_parser.get("zabbix", "host_groups")
    except configparser.NoOptionError as e:
        logger.warning("Skipping %s — missing config key: %s", config_file, e)
        return []

    host_groups = [x.strip() for x in host_groups_raw.split("|") if x.strip()]

    try:
        zapi = ZabbixAPI(server=zabbix_url, timeout=30)
        zapi.session.verify = False
        zapi.login(user=zabbix_user, password=zabbix_password)
        logger.info("Connected to Zabbix %s (API %s)", zabbix_url, zapi.api_version())
    except Exception as e:
        logger.error("Failed to connect to Zabbix at %s: %s", zabbix_url, e)
        return []

    if host_groups:
        hg_res = zapi.do_request("hostgroup.get", {"output": "extend", "filter": {"name": host_groups}})
    else:
        hg_res = zapi.do_request("hostgroup.get", {"output": "extend"})
    hg_ids = [item["groupid"] for item in hg_res["result"]]

    if not hg_ids:
        logger.warning("No host groups matched in %s", config_file)
        return []

    hosts_res = zapi.do_request("host.get", {
        "output": ["name", "hostid"],
        "groupids": hg_ids,
        "selectInterfaces": ["ip", "type", "main"],
        "selectTags": "extend",
    })

    hosts = []
    for item in hosts_res["result"]:
        ip = ""
        for iface in item.get("interfaces") or []:
            if iface.get("main") == "1" and iface.get("type") == "1":
                ip = iface.get("ip", "")
                break
        if not ip:
            for iface in item.get("interfaces") or []:
                if iface.get("ip"):
                    ip = iface.get("ip", "")
                    break

        jira_key = None
        for tag in item.get("tags") or []:
            if tag.get("tag") == "jira_device_key":
                jira_key = tag.get("value") or None
                break

        hosts.append({"hostid": item["hostid"], "name": item["name"], "ip": ip, "jira_key": jira_key})

    logger.info("Config %s: %d host(s) across %d group(s)",
                Path(config_file).name, len(hosts), len(hg_ids))
    return hosts


def main():
    parser = argparse.ArgumentParser(description="Sync Zabbix hosts against the AccessParks device inventory.")
    parser.add_argument("--workers", type=int, default=20,
                        help="Number of parallel inventory API workers (default: 20)")
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    conf_d = script_dir / "conf.d"
    config_files = sorted(glob.glob(str(conf_d / "*.ini")))

    if not config_files:
        logger.error("No *.ini files found in %s", conf_d)
        return

    matched_path = script_dir / "devicelookup.json"
    not_found_path = script_dir / "devicelookupnotfound.json"

    # Load existing data — baseline; we update entries in-place, never start from scratch
    matched = {}
    not_found = {}
    for path, target in ((matched_path, matched), (not_found_path, not_found)):
        if path.exists():
            try:
                target.update(json.loads(path.read_text()))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Could not load existing %s: %s", path.name, e)

    # Collect all unique hosts across configs (dedup by hostid)
    all_hosts = {}
    for config_file in config_files:
        for host in collect_hosts_from_config(config_file):
            all_hosts[host["hostid"]] = host

    # Safety gate 1: Zabbix returned nothing — server may be down, don't touch files
    if not all_hosts:
        logger.warning("No hosts collected from Zabbix — JSON files not updated")
        return

    total = len(all_hosts)
    logger.info("Total unique hosts to process: %d  (workers: %d)", total, args.workers)

    # Thread-safe counters and result accumulator
    lock = threading.Lock()
    error_count = 0
    update_count = 0
    completed = 0
    results = []   # list of (hostid, host, ident_used, device, had_error)

    def lookup_one(item):
        hostid, host = item
        ident_used, device, had_error = find_in_inventory(host)
        return hostid, host, ident_used, device, had_error

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(lookup_one, item): item[0]
                   for item in all_hosts.items()}

        for future in as_completed(futures):
            hostid, host, ident_used, device, had_error = future.result()

            with lock:
                completed += 1
                if completed % 500 == 0 or completed == total:
                    logger.info("Progress: %d/%d (%.0f%%)", completed, total, completed / total * 100)

                if had_error:
                    error_count += 1
                    logger.warning("API error — preserved existing entry for hostid=%s", hostid)
                    continue

                update_count += 1
                if device:
                    matched[hostid] = {"host": host, "identifier_used": ident_used, "device": device}
                    not_found.pop(hostid, None)
                else:
                    not_found[hostid] = {"host": host}
                    matched.pop(hostid, None)

    # Safety gate 2: every single lookup failed — inventory server is likely down
    if update_count == 0:
        logger.error(
            "All %d inventory lookups returned API errors — inventory server may be down. "
            "JSON files NOT overwritten to preserve existing data.", error_count
        )
        return

    if error_count > 0:
        logger.warning(
            "%d/%d hosts had API errors and were skipped — their existing entries are preserved",
            error_count, total
        )

    # Atomic writes — temp file + rename so a crash never leaves a corrupt file
    matched["lastmodifiedtimedata"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    atomic_write_json(matched_path, matched)
    atomic_write_json(not_found_path, not_found)

    matched_count = sum(1 for k in matched if k != "lastmodifiedtimedata")
    logger.info(
        "Done. Matched: %d | Not found: %d | Errors (skipped): %d | Total hosts: %d",
        matched_count, len(not_found), error_count, total
    )


if __name__ == "__main__":
    main()
