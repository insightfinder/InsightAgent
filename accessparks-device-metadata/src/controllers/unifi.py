"""UniFi controller — Site Manager API (api.ui.com).

Ported from InsightAgent/unifi-agent/get_metrics.py (list_sites,
fetch_site_devices_legacy). Sites are only a traversal step to reach the
per-site device list — they are not part of ControllerDevice.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request

from models import ControllerDevice

logger = logging.getLogger(__name__)

SITE_MANAGER_BASE = "https://api.ui.com"


def _api_get(url: str, api_key: str, retries: int = 1) -> dict:
    """GET url, retrying up to `retries` times. Every path either returns a
    parsed response or raises RuntimeError — there is no other way out of the
    loop."""
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
    raise AssertionError("unreachable")
    return {}


def _list_sites(api_key: str) -> list[dict]:
    data = _api_get(f"{SITE_MANAGER_BASE}/v1/sites?pageSize=200", api_key)
    return [
        {"hostId": entry["hostId"], "siteSlug": entry["meta"]["name"]}
        for entry in data.get("data", [])
    ]


def _fetch_site_devices(host_id: str, site_slug: str, api_key: str) -> list[dict]:
    url = f"{SITE_MANAGER_BASE}/v1/connector/consoles/{host_id}/proxy/network/api/s/{site_slug}/stat/device"
    try:
        return _api_get(url, api_key, retries=2).get("data", [])
    except RuntimeError as e:
        logger.warning("%s", e)
        return []


class UnifiController:
    name = "UniFi"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def list_devices(self) -> list[ControllerDevice]:
        sites = _list_sites(self.api_key)
        logger.info("UniFi: found %d site(s)", len(sites))

        devices: list[ControllerDevice] = []
        for site in sites:
            raw_devices = _fetch_site_devices(site["hostId"], site["siteSlug"], self.api_key)
            for d in raw_devices:
                devices.append(
                    ControllerDevice(
                        controller=self.name,
                        name=d.get("name") or "",
                        ip=d.get("ip") or "",
                        mac=(d.get("mac") or "").upper(),
                        serial=d.get("serial") or "",
                        device_id=d.get("device_id") or "",
                    )
                )
        logger.info("UniFi: collected %d device(s) total", len(devices))
        return devices
