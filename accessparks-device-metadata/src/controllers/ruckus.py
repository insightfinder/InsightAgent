"""Ruckus controller — SmartZone WSG (Wi-Fi Service Gateway) public API.

Ported from InsightAgent/ruckus-agent (ruckus/ruckus.go, ruckus/type.go,
ruckus/get_bulk_ap_data.go) — AP listing only. The reference agent also fetches
/query/client (per-AP RSSI/SNR metric enrichment) and calls out to a separate
InsightFinder-side Device Inventory API for name/serial overrides; neither is
device *discovery* — this repo's jira_assets.py/reconcile.py already plays the
enrichment/reconciliation role generically, so both are skipped here.

Deliberate simplification over the reference: it proactively re-authenticates
every 30 minutes (a background timer) because it runs as a long-lived polling
daemon. This agent makes one pass per invocation and a full AP listing
completes in seconds, so that timer would never fire — only the reactive path
(re-login on a session-expired 401) is ported.

Auth is cookie-session (JSESSIONID), not a bearer token: POST .../session sets
the cookie via Set-Cookie, and a requests.Session's cookie jar carries it on
every later call automatically — never extract/replay it by hand. This is the
same idiom mimosa.py already uses for its own cookie-session login.

RUCKUS_API_VERSION selects the path segment (v10_0 for SmartZone 5.x, v11_0/
v11_1 for 6.x) — unverified against the live controller as of this port (see
README.md's Ruckus section); confirm and correct it once network access to the
controller is available.
"""

from __future__ import annotations

import logging

import requests

from models import ControllerDevice

logger = logging.getLogger(__name__)

PAGE_LIMIT = 500


class RuckusController:
    name = "Ruckus"

    def __init__(self, base_url: str, username: str, password: str, api_version: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.api_base = f"{self.base_url}/wsg/api/public/{api_version}"

    def _login(self) -> requests.Session:
        session = requests.Session()
        resp = session.post(
            f"{self.api_base}/session",
            json={"username": self.username, "password": self.password},
            verify=False,
            timeout=15,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Ruckus login failed with status {resp.status_code}: {resp.text[:200]}")
        return session

    @staticmethod
    def _is_session_expired(resp: requests.Response) -> bool:
        # The controller signals an expired session with a 401 whose JSON body
        # carries {"code": 201, ...} specifically — any other 401 is a genuine
        # auth/permission failure and must not be silently retried.
        if resp.status_code != 401:
            return False
        try:
            return resp.json().get("code") == 201
        except ValueError:
            return False

    def _query_ap_page(self, session: requests.Session, page: int) -> dict:
        resp = session.post(
            f"{self.api_base}/query/ap",
            json={"filters": [], "page": page, "limit": PAGE_LIMIT},
            verify=False,
            timeout=30,
        )
        if self._is_session_expired(resp):
            session = self._login()
            resp = session.post(
                f"{self.api_base}/query/ap",
                json={"filters": [], "page": page, "limit": PAGE_LIMIT},
                verify=False,
                timeout=30,
            )
        resp.raise_for_status()
        return resp.json()

    def list_devices(self) -> list[ControllerDevice]:
        session = self._login()

        all_aps: list[dict] = []
        page = 1  # Ruckus pagination is 1-based, not 0-based.
        while True:
            body = self._query_ap_page(session, page)
            items = body.get("list") or []
            all_aps.extend(items)

            total_count = body.get("totalCount", len(all_aps))
            if len(all_aps) >= total_count or not items:
                break
            page += 1

        devices: list[ControllerDevice] = []
        for ap in all_aps:
            devices.append(
                ControllerDevice(
                    controller=self.name,
                    name=ap.get("deviceName") or "",
                    ip=ap.get("ip") or "",
                    mac=(ap.get("apMac") or "").upper(),
                    serial=ap.get("serial") or "",
                )
            )
        logger.info("Ruckus: collected %d device(s) total", len(devices))
        return devices
