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
v11_1 for 6.x). Confirmed live: `GET /wsg/api/public/apiInfo` reports
v9_0, v9_1, v10_0, v11_0 and v11_1, and `query/ap` was verified working on
each — the pinned v11_1 is correct for this deployment.

Devices come from `GET /aps`, and IP is enriched from `POST /query/ap`
afterwards, because `query/ap` alone cannot be relied on to enumerate this
fleet: some AP record in it makes the controller answer HTTP 500
({"message": "For input string: \"\""}) for whichever page that record lands
on. At the original page size of 500 that was page 2 onward (reproduced 3/3),
and at 100 it was page 9 — persistent across retries, and the exception took
the entire controller down to zero devices on every run. The poisoned page
moves as the fleet changes, so no page size or retry count avoids it.

`GET /aps` pages cleanly through all 3,726 APs and carries name/mac/serial —
every identifier reconciliation needs. It has no `ip`, so `query/ap` is still
walked for that, page by page, and a page that keeps failing is skipped with a
warning rather than aborting: a missing IP costs the Zabbix IP fallback for
those APs, while a raised exception costs every AP the controller has.
`ip=""` on a given run is therefore expected for a subset, as it already is
for Baicells.
"""

from __future__ import annotations

import logging
import time

import requests

from jira_assets import mac_key
from models import ControllerDevice

logger = logging.getLogger(__name__)

PAGE_LIMIT = 100
PAGE_RETRIES = 3
LIST_PAGE_SIZE = 500
MAX_SKIPPED_PAGES = 5
# A session-expired 401 is answered by logging in again, which is only ever a
# recovery from an *expiring* session. A controller that answers every request
# with one (a session-limit or a permissions change) would otherwise have this
# agent re-logging-in forever, hanging the cron run and spending a fresh
# SmartZone session each time.
MAX_RELOGINS = 3


def _ip_join_key(mac: str) -> str:
    """Key for joining GET /aps rows to query/ap rows.

    Both endpoints report colon-uppercase MACs today, but they are two
    different serializers on the same controller, so the join is normalized
    rather than trusted: a separator change on either side would otherwise
    silently zero IP enrichment across the whole fleet. Falls back to the
    upper-cased raw value for anything mac_key rejects as not-a-MAC, so such
    rows still join to themselves instead of collapsing onto one "" key.
    """
    return mac_key(mac) or mac.strip().upper()


class RuckusController:
    name = "Ruckus"

    def __init__(self, base_url: str, username: str, password: str, api_version: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.api_base = f"{self.base_url}/wsg/api/public/{api_version}"
        # Held on the instance, not passed around: a re-login mid-run has to be
        # visible to every later request, and a session rebound to a local
        # variable would leave the *next* call still holding the expired one.
        self._session: requests.Session | None = None
        self._relogins = 0

    def _login(self) -> requests.Session:
        session = requests.Session()
        resp = session.post(
            f"{self.api_base}/session",
            json={"username": self.username, "password": self.password},
            verify=False,
            timeout=15,
        )
        if resp.status_code != 200:
            session.close()
            raise RuntimeError(f"Ruckus login failed with status {resp.status_code}: {resp.text[:200]}")
        self._session = session
        return session

    def _relogin(self) -> requests.Session:
        """Replaces the expired session, bounded so a controller that rejects
        every session can't spin here. The old session is closed rather than
        abandoned — SmartZone caps concurrent sessions per account."""
        self._relogins += 1
        if self._relogins > MAX_RELOGINS:
            raise RuntimeError(
                f"Ruckus reported an expired session {MAX_RELOGINS} times in one run — refusing to "
                "keep re-authenticating (check the account's concurrent-session limit and permissions)"
            )
        if self._session is not None:
            self._session.close()
        return self._login()

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

    def _query_ap_page(self, page: int) -> dict:
        resp = self._post_query_ap(page)
        if self._is_session_expired(resp):
            self._relogin()
            resp = self._post_query_ap(page)
        # A page fetch is a pure read, so a 5xx is retried before the page is
        # given up on. The poisoned page described in the module docstring
        # survives these retries by design — they're here for ordinary
        # transient faults; _collect_ips is what tolerates the persistent one.
        for attempt in range(1, PAGE_RETRIES + 1):
            if resp.status_code < 500 or attempt == PAGE_RETRIES:
                break
            logger.warning(
                "Ruckus: query/ap page %d returned %d (attempt %d/%d) — retrying",
                page,
                resp.status_code,
                attempt,
                PAGE_RETRIES,
            )
            time.sleep(attempt)
            resp = self._post_query_ap(page)
        resp.raise_for_status()
        return resp.json()

    def _post_query_ap(self, page: int) -> requests.Response:
        return self._session.post(
            f"{self.api_base}/query/ap",
            json={"filters": [], "page": page, "limit": PAGE_LIMIT},
            verify=False,
            timeout=30,
        )

    def list_devices(self) -> list[ControllerDevice]:
        self._login()
        try:
            all_aps = self._list_aps()
            ips = self._collect_ips()
        finally:
            if self._session is not None:
                self._session.close()
                self._session = None

        devices: list[ControllerDevice] = []
        for ap in all_aps:
            mac = (ap.get("mac") or "").upper()
            devices.append(
                ControllerDevice(
                    controller=self.name,
                    name=ap.get("name") or "",
                    ip=ips.get(_ip_join_key(mac), ""),
                    mac=mac,
                    serial=ap.get("serial") or "",
                )
            )
        logger.info(
            "Ruckus: collected %d device(s) total (%d with an IP)",
            len(devices),
            sum(1 for d in devices if d.ip),
        )
        return devices

    def _list_aps(self) -> list[dict]:
        """GET /aps — the authoritative AP list (name/mac/serial), index-paged.

        Unlike query/ap this endpoint is reliable, so a failure here is real
        and aborts the controller rather than being skipped: without it there
        is no device list to report at all.
        """
        aps: list[dict] = []
        index = 0
        while True:
            resp = self._session.get(
                f"{self.api_base}/aps",
                params={"index": index, "listSize": LIST_PAGE_SIZE},
                verify=False,
                timeout=60,
            )
            if self._is_session_expired(resp):
                self._relogin()  # bounded — see MAX_RELOGINS
                continue
            resp.raise_for_status()
            body = resp.json()
            batch = body.get("list") or []
            aps.extend(batch)
            if not body.get("hasMore") or not batch:
                break
            index += len(batch)
        return aps

    def _collect_ips(self) -> dict[str, str]:
        """MAC -> IP from query/ap, best effort.

        Every per-page failure mode is skippable, not just a 5xx: a read
        timeout, a dropped connection or a truncated body on one page must not
        discard the complete device list _list_aps already returned — which is
        the whole reason devices don't come from this endpoint. A 4xx is
        re-raised: that's an auth or contract problem affecting every page, not
        one poisoned record.
        """
        ips: dict[str, str] = {}
        skipped = 0
        page = 1  # Ruckus pagination is 1-based, not 0-based.
        while True:
            try:
                body = self._query_ap_page(page)
            except (requests.exceptions.RequestException, ValueError) as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status is not None and status < 500:
                    raise
                skipped += 1
                logger.warning(
                    "Ruckus: query/ap page %d failed (%s) — skipping it; those AP(s) will be "
                    "reported without an IP",
                    page,
                    status or type(e).__name__,
                )
                page += 1
                if skipped > MAX_SKIPPED_PAGES:
                    logger.error(
                        "Ruckus: %d query/ap page(s) failed — abandoning IP enrichment, "
                        "devices are still reported from GET /aps",
                        skipped,
                    )
                    break
                continue
            items = body.get("list") or []
            for ap in items:
                mac = ap.get("apMac") or ""
                if mac and ap.get("ip"):
                    ips[_ip_join_key(mac)] = ap["ip"]
            total_count = body.get("totalCount")
            if not items or (total_count is not None and page * PAGE_LIMIT >= total_count):
                break
            page += 1
        return ips
