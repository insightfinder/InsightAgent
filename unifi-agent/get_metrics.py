#!/usr/bin/env python3
"""Fetch channel utilization (Busy/Rx/Tx %) per radio for all UniFi access points across all sites."""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

SITE_MANAGER_BASE = "https://api.ui.com"
BAND_MAP = {"ng": "2.4GHz", "na": "5GHz", "6e": "6GHz", "60g": "60GHz"}
SUPPORTED_BANDS = frozenset({"2.4GHz", "5GHz"})


def load_env(path: Path | str) -> dict:
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                val = val.strip()
                if val and val[0] in ('"', "'"):
                    quote = val[0]
                    end = val.find(quote, 1)
                    val = val[1:end] if end != -1 else val.strip(quote)
                else:
                    val = val.split("#")[0].strip()
                env[key.strip()] = val
    except FileNotFoundError:
        pass
    return env


def api_get(url: str, api_key: str, retries: int = 1) -> dict:
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "X-API-Key": api_key},
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            if e.code in (401, 403, 404, 422):
                raise RuntimeError(f"HTTP {e.code} {url}\n  {body}") from None
            if attempt == retries:
                raise RuntimeError(f"HTTP {e.code} {url}\n  {body}") from None
            time.sleep(1)
        except urllib.error.URLError as e:
            if attempt == retries:
                raise RuntimeError(f"Request failed {url}: {e}") from None
            time.sleep(1)
    return {}


def list_sites(api_key: str) -> list[dict]:
    url = f"{SITE_MANAGER_BASE}/v1/sites?pageSize=200"
    data = api_get(url, api_key)
    return [
        {
            "hostId": entry["hostId"],
            "siteSlug": entry["meta"]["name"],
            "siteName": entry["meta"]["desc"],
        }
        for entry in data.get("data", [])
    ]


def fetch_site_devices_legacy(host_id: str, site_slug: str, api_key: str, retries: int = 1) -> list[dict] | None:
    url = (
        f"{SITE_MANAGER_BASE}/v1/connector/consoles/{host_id}"
        f"/proxy/network/api/s/{site_slug}/stat/device"
    )
    try:
        return api_get(url, api_key, retries=retries).get("data", [])
    except RuntimeError as e:
        logger.warning("%s", e)
        return None


def band_label(radio_code: str) -> str:
    return BAND_MAP.get(radio_code, radio_code or "?")



def extract_radio_rows(ap: dict, site_name: str) -> list[dict]:
    name = ap.get("name", "")
    ip = ap.get("ip", "")
    state = ap.get("state")
    if isinstance(state, int):
        status = "online" if state == 1 else "offline"
    elif isinstance(state, str):
        status = state.lower()
    else:
        status = "online" if ap.get("uptime") else "offline"

    radio_table = {r["name"]: r for r in ap.get("radio_table", []) if "name" in r}
    radio_stats = {r["name"]: r for r in ap.get("radio_table_stats", []) if "name" in r}

    rows = []
    for rname in sorted(set(radio_table) | set(radio_stats)):
        cfg = radio_table.get(rname, {})
        stats = radio_stats.get(rname, {})
        rows.append({
            "site": site_name,
            "ap_name": name,
            "ip": ip,
            "band": band_label(cfg.get("radio", stats.get("radio", ""))),
            "ChUtil_Busy": stats.get("cu_total"),
            "ChUtil_Rx": stats.get("cu_self_rx"),
            "ChUtil_Tx": stats.get("cu_self_tx"),
            "status": status,
        })

    if not rows:
        rows.append({
            "site": site_name,
            "ap_name": name,
            "ip": ip,
            "band": "-",
            "ChUtil_Busy": None,
            "ChUtil_Rx": None,
            "ChUtil_Tx": None,
            "status": status,
        })
    return rows


def collect_ap_rows(api_key: str, sites: list[dict] | None = None) -> list[dict]:
    """Fetch radio rows for every AP across all sites."""
    if sites is None:
        sites = list_sites(api_key)
        logger.info("Found %d sites across %d console(s).", len(sites), len({s['hostId'] for s in sites}))

    all_rows: list[dict] = []
    by_host: dict[str, list[dict]] = {}
    for s in sites:
        by_host.setdefault(s["hostId"], []).append(s)

    total = len(sites)
    done = 0
    failed_sites: list[str] = []
    for host_id, host_sites in by_host.items():
        for site in host_sites:
            name = site["siteName"]
            done += 1
            logger.info("[%d/%d] Fetching %s...", done, total, name)
            devices = fetch_site_devices_legacy(host_id, site["siteSlug"], api_key, retries=2)

            if devices is None:
                logger.warning("Skipping [%s] due to API error; will retry next cycle.", name)
                failed_sites.append(name)
                continue

            time.sleep(0.1)

            ap_devices = [d for d in devices if d.get("type") == "uap"]
            if not ap_devices:
                ap_devices = [d for d in devices if "radio_table" in d or "radio_table_stats" in d]
            for ap in ap_devices:
                all_rows.extend(extract_radio_rows(ap, name))

    if failed_sites and not all_rows:
        raise SystemExit(
            "ERROR: Legacy API path /proxy/network/api/s/{site}/stat/device is blocked through\n"
            "Cloud Connector for all sites. Options:\n"
            "  1. Request direct controller access credentials (README §How to resolve).\n"
            "  2. Use the web UI to read values manually.\n"
            f"Failed sites: {', '.join(failed_sites)}"
        )
    if failed_sites:
        logger.warning("Partial results: %d site(s) failed to fetch: %s", len(failed_sites), ", ".join(failed_sites))

    return all_rows


def print_table(rows: list[dict]) -> None:
    if not rows:
        print("No rows to display.")
        return
    cols = ["site", "ap_name", "band", "ChUtil_Busy", "ChUtil_Rx", "ChUtil_Tx", "status"]
    str_rows = [{c: "" if (v := r.get(c)) is None else str(v) for c in cols} for r in rows]
    widths = {c: max(len(c), max(len(sr[c]) for sr in str_rows)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    print("  ".join("-" * widths[c] for c in cols))
    current_site = None
    for sr in str_rows:
        if sr["site"] != current_site:
            if current_site is not None:
                print()
            current_site = sr["site"]
        print("  ".join(sr[c].ljust(widths[c]) for c in cols))


def main() -> None:
    env_path = Path(__file__).parent / ".env"
    env = load_env(env_path)
    api_key = env.get("UNIFI_API_KEY") or os.environ.get("UNIFI_API_KEY")
    if not api_key:
        raise SystemExit("UNIFI_API_KEY not set in .env or environment.")

    print("Fetching sites...")
    all_rows = collect_ap_rows(api_key)
    print()
    all_rows.sort(key=lambda r: (r["site"], r["ap_name"], r["band"]))

    seen: set[tuple[str, str]] = set()
    online = offline = 0
    for r in all_rows:
        key = (r["site"], r["ap_name"])
        if key not in seen:
            seen.add(key)
            if r["status"] == "online":
                online += 1
            else:
                offline += 1
    print(f"Devices: {online} online, {offline} offline ({online + offline} total)\n")

    print_table(all_rows)


if __name__ == "__main__":
    main()
