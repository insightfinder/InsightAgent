"""Client for the AccessParks Asset Registry service — a local mirror of Jira
Assets, exposing `GET /devices/{identifier}` (see
InsightAgent/ap-jira-asset-server). This is what every existing AccessParks
agent talks to instead of Jira Assets/AQL directly.

Lookup contract mirrors InsightAgent/unifi-agent/ap_inventory_lookup.py:
  - {}   -> confirmed miss (404)
  - None -> API/network error; caller must NOT treat this as a confirmed miss
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from models import JiraMatch

logger = logging.getLogger(__name__)


class JiraAssetClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def health_ok(self) -> bool:
        try:
            req = urllib.request.Request(
                f"{self.base_url}/health",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read()).get("status") == "ok"
        except (urllib.error.URLError, ValueError, OSError) as e:
            logger.error("Asset Registry health check failed: %s", e)
            return False

    def lookup(self, identifier: str) -> dict | None:
        """GET /devices/{identifier}. Returns the device record ({} = not
        found) or None on request error."""
        url = f"{self.base_url}/devices/{urllib.parse.quote(identifier, safe='')}"
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "X-API-Key": self.api_key},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}
            logger.warning("HTTP %d looking up %r in Jira Assets", e.code, identifier)
            return None
        except (urllib.error.URLError, ValueError, OSError) as e:
            logger.warning("Jira Assets request failed for %r: %s", identifier, e)
            return None

    def find_device(self, mac: str, serial: str, name: str) -> tuple[JiraMatch | None, bool]:
        """Try identifiers in priority order: MAC -> serial -> name. IP is
        deliberately excluded — it isn't stable enough to key identity on.

        Stops at the first identifier that errors (same contract as
        ap_inventory_lookup.py's find_in_inventory) so a transient failure on
        one identifier can't be misread as "tried everything, confirmed
        missing" — the caller must not report this device as missing.

        Returns (match, had_error).
        """
        for ident in (mac, serial, name):
            if not ident:
                continue
            result = self.lookup(ident)
            if result is None:
                return None, True  # error — stop, don't treat as a miss
            if result:
                return (
                    JiraMatch(
                        object_key=result.get("object_key") or "",
                        ip=result.get("ip_address") or "",
                        mac=(result.get("mac_address") or "").upper(),
                        zabbix_host_id=result.get("zabbix_host_id") or "",
                    ),
                    False,
                )
        return None, False  # all identifiers tried, all returned 404
