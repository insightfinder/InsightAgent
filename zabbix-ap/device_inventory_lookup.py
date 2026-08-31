#!/usr/bin/env python3
"""
Match every Zabbix host against the AccessParks device inventory.

Identifier priority per host: jira_device_key tag → zabbix_host_id → ip_address.

Reads all conf.d/*.ini files to collect host_groups and connect to each Zabbix
instance, then does exactly ONE bulk GET /devices/export call against the
asset server and matches every host against it in memory — mirrors the
jira-metadata agent's bulk-export pattern instead of one inventory API
request per host.

Can be run standalone (cron) or imported: getmessages_zabbix.py calls
run_refresh() directly when devicelookup.json goes stale, so the lookup used
for metric enrichment never depends on a separate cron job actually existing.

Outputs (same directory as this script):
  devicelookup.json         — hosts found (zabbix_host_id → {host, identifier_used, device})
  devicelookupnotfound.json — hosts with no match (zabbix_host_id → {host})

Safety guarantees:
  - Files are never overwritten if Zabbix returns no hosts (Zabbix down).
  - Files are never overwritten if the bulk export fails or returns nothing
    (inventory server down/empty).
  - Writes are atomic (temp file + rename) so a crash mid-write never corrupts the file.

Usage:
  python device_inventory_lookup.py
"""

import argparse
import configparser
import datetime
import glob
import json
import logging
import time
from pathlib import Path

import requests
from pyzabbix import ZabbixAPI

requests.packages.urllib3.disable_warnings()

logger = logging.getLogger(__name__)

# Fallback defaults — normally overridden by device_inventory_api_key /
# device_inventory_base_url in the [zabbix] section of conf.d/*.ini.
INVENTORY_BASE_URL = ""
INVENTORY_API_KEY = ""
INVENTORY_TIMEOUT_SEC = 120

DEVICE_LOOKUP_REFRESH_HOURS_DEFAULT = 24

# Shared session — connection pooling, keep-alive
_session = requests.Session()
_session.verify = False


def load_inventory_credentials(config_files):
    """Read device_inventory_api_key/base_url/timeout_sec from the [zabbix] section
    of the first config file that has them — the asset server is shared across all
    Zabbix instances, so one set of credentials covers every conf.d/*.ini.
    Falls back to the module-level constants (blank key) if none is configured."""
    for config_file in config_files:
        config_parser = configparser.ConfigParser(interpolation=None)
        config_parser.read(config_file)
        api_key = config_parser.get("zabbix", "device_inventory_api_key", fallback="")
        if api_key:
            base_url = config_parser.get("zabbix", "device_inventory_base_url", fallback=INVENTORY_BASE_URL)
            timeout = config_parser.getint("zabbix", "device_inventory_timeout_sec", fallback=INVENTORY_TIMEOUT_SEC)
            return api_key, base_url, timeout
    logger.warning("device_inventory_api_key not set in any conf.d/*.ini — bulk export will fail auth")
    return INVENTORY_API_KEY, INVENTORY_BASE_URL, INVENTORY_TIMEOUT_SEC


def device_lookup_is_stale(path, refresh_hours=DEVICE_LOOKUP_REFRESH_HOURS_DEFAULT):
    """Return True if the devicelookup.json at `path` is missing or older than refresh_hours."""
    p = Path(path)
    if not p.exists():
        return True
    age_hours = (time.time() - p.stat().st_mtime) / 3600
    return age_hours >= refresh_hours


def export_devices(base_url: str, api_key: str, timeout: int = INVENTORY_TIMEOUT_SEC):
    """Bulk-fetch every device in one call via GET /devices/export (same pattern as
    the jira-metadata agent's exportDevices) instead of one request per host.
    Returns:
      list of dicts  — success (may be empty)
      None           — network/server error (caller should treat as API down)
    """
    url = "{}/devices/export".format(base_url.rstrip("/"))
    headers = {"Accept": "application/json", "X-API-Key": api_key}
    try:
        resp = _session.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except requests.RequestException as e:
        logger.warning("Bulk device export failed: %s", e)
        return None


def build_device_index(devices: list):
    """Build in-memory lookup indexes over the bulk-exported devices, keyed by
    zabbix_host_id, jira object_key, and ip_address (case-insensitive) — mirrors
    jira-metadata/main.go's deviceIndex, built once per run instead of one HTTP
    request per identifier."""
    by_zabbix_id, by_object_key, by_ip = {}, {}, {}
    for d in devices:
        zid = (d.get("zabbix_host_id") or "").strip().lower()
        if zid:
            by_zabbix_id[zid] = d
        okey = (d.get("object_key") or "").strip().lower()
        if okey:
            by_object_key[okey] = d
        ip = (d.get("ip_address") or "").strip().lower()
        if ip:
            by_ip[ip] = d
    return {"zabbix_id": by_zabbix_id, "object_key": by_object_key, "ip": by_ip}


def find_in_inventory(host: dict, index: dict):
    """Try identifiers in priority order against the local index: jira_device_key
    → zabbix_host_id → ip. Purely in-memory — no network calls.

    jira_device_key is a Zabbix host tag whose value is the inventory object_key (e.g. IHS-23344).

    Returns (ident, device_dict) on match, else (None, None).
    """
    jira_key = (host.get("jira_key") or "").strip().lower()
    if jira_key and jira_key in index["object_key"]:
        return host["jira_key"], index["object_key"][jira_key]

    hostid = str(host["hostid"]).strip().lower()
    if hostid in index["zabbix_id"]:
        return host["hostid"], index["zabbix_id"][hostid]

    ip = (host.get("ip") or "").strip().lower()
    if ip and ip in index["ip"]:
        return host["ip"], index["ip"][ip]

    return None, None


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


def run_refresh(config_files, api_key=None, base_url=None, timeout=None, script_dir=None):
    """Refresh devicelookup.json / devicelookupnotfound.json with one bulk
    GET /devices/export call, matched locally against every Zabbix host found
    in config_files. Safe to call from another process (e.g. getmessages_zabbix.py)
    on a staleness check — never touches the files on a failed/empty export.

    Returns True if the files were updated, False otherwise.
    """
    script_dir = script_dir or Path(__file__).parent
    if api_key is None or base_url is None or timeout is None:
        cred_key, cred_url, cred_timeout = load_inventory_credentials(config_files)
        api_key = api_key if api_key is not None else cred_key
        base_url = base_url if base_url is not None else cred_url
        timeout = timeout if timeout is not None else cred_timeout

    matched_path = script_dir / "devicelookup.json"
    not_found_path = script_dir / "devicelookupnotfound.json"

    # Load existing data — baseline; matches/not-founds are overwritten wholesale
    # on success, but kept as-is if any safety gate below trips.
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
        return False

    logger.info("Bulk-exporting device inventory from %s ...", base_url)
    devices = export_devices(base_url, api_key, timeout)

    # Safety gate 2: export failed (network/auth/server error) — keep existing data
    if devices is None:
        logger.warning(
            "Device export API unreachable — JSON files not updated (%d hosts pending)", len(all_hosts))
        return False

    # Safety gate 3: export succeeded but returned nothing — asset server likely empty/down
    if not devices:
        logger.warning("Device export returned 0 devices — JSON files not updated")
        return False

    total = len(all_hosts)
    logger.info("Fetched %d devices; matching against %d hosts", len(devices), total)
    index = build_device_index(devices)

    for hostid, host in all_hosts.items():
        ident_used, device = find_in_inventory(host, index)
        if device:
            matched[hostid] = {"host": host, "identifier_used": ident_used, "device": device}
            not_found.pop(hostid, None)
        else:
            not_found[hostid] = {"host": host}
            matched.pop(hostid, None)

    # Atomic writes — temp file + rename so a crash never leaves a corrupt file
    matched["lastmodifiedtimedata"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    atomic_write_json(matched_path, matched)
    atomic_write_json(not_found_path, not_found)

    matched_count = sum(1 for k in matched if k != "lastmodifiedtimedata")
    logger.info(
        "Done. Matched: %d | Not found: %d | Total hosts: %d",
        matched_count, len(not_found), total
    )
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                         datefmt="%Y-%m-%d %H:%M:%S")
    parser = argparse.ArgumentParser(description="Sync Zabbix hosts against the AccessParks device inventory.")
    parser.parse_args()

    script_dir = Path(__file__).parent
    conf_d = script_dir / "conf.d"
    config_files = sorted(glob.glob(str(conf_d / "*.ini")))

    if not config_files:
        logger.error("No *.ini files found in %s", conf_d)
        return

    run_refresh(config_files, script_dir=script_dir)


if __name__ == "__main__":
    main()
