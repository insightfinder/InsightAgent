"""Cambium controller — cnMaestro Cloud (cloud.cambiumnetworks.com).

cnMaestro's documented API is OAuth2 client-credentials (a client id/secret
generated in its UI), not the email/password this account has — so, per the
existing InsightAgent cambium-agent (cambium/cambium.go), auth is done by
driving the real login SPA with Playwright and lifting the resulting session
cookies, then hitting the JSON API directly with plain `requests`.

CAMBIUM_BASE_URL may be a comma-separated list — cnMaestro tenant base URLs
embed a site (NMS account) name (e.g. .../LAKEMEAD1/cn-srv), so multiple
sites are a config change here, not a code change. Each site gets its own
login+navigate pass since that's what mints its site-scoped cookies.

This account has more than one NMS account (e.g. "LAKEMEAD1" and
"AP_CNMAESTRO_X_ONLY_DEVICES") and login lands on an account-picker screen —
navigating straight to the tenant API path without first clicking the
matching account tile leaves the session scoped to nothing, and the API
responds 401 "session is expired" even on the very first request (verified
live; this step is not present in the InsightAgent reference, which appears
to assume a single-account login). The account name is taken from the site
segment of CAMBIUM_BASE_URL.

Unlike the reference agent (which fetches one unpaged page and ignores the
totalCount it gets back), this pages using data._metadata until exhausted.
Device serial (`sn`, top-level) is also present in the live payload despite
the reference's Device struct omitting it.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import requests

from models import ControllerDevice

logger = logging.getLogger(__name__)

LOGIN_URL = "https://cloud.cambiumnetworks.com/#/"
PAGE_LIMIT = 200


def _site_name(base_url: str) -> str:
    """Extract the NMS account/site name from a tenant base URL, e.g.
    'https://.../LAKEMEAD1/cn-srv' -> 'LAKEMEAD1'."""
    parts = [p for p in base_url.rstrip("/").split("/") if p]
    return parts[-2] if len(parts) >= 2 else parts[-1]


def _login_and_get_cookies(login_url: str, devices_url: str, site_name: str, email: str, password: str) -> dict[str, str]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(login_url)
            page.locator("button:has-text('Sign In'), a[role='button']:has-text('Sign In')").click()
            page.locator("input[type='email'], input[name*='email'], input[placeholder*='email' i]").fill(
                email
            )
            page.locator("text=Next").click()
            page.locator("input[type='password'], input[name*='password']").fill(password)
            remember_me = page.locator("input[type='checkbox']")
            if remember_me.count():
                remember_me.check()
            page.locator(
                "button:has-text('Sign In'), input[type='submit'][value*='Sign In'],"
                " a[role='button']:has-text('Sign In')"
            ).click()
            page.wait_for_timeout(3000)

            # An account with more than one NMS account lands on a picker here.
            # Clicking the matching tile is what actually scopes the session to
            # this tenant — skipping it leaves the API rejecting every request as
            # "session expired", even the very first one.
            account_tile = page.get_by_role("button", name=f"{site_name} NMS Account")
            if account_tile.count():
                account_tile.click()
                page.wait_for_timeout(3000)

            # Navigating to the devices URL is what mints cookies scoped to this
            # tenant's API path — skipping it leaves sid/XSRF-TOKEN unset.
            page.goto(devices_url)
            page.wait_for_timeout(1000)

            cookies = {c["name"]: c["value"] for c in page.context.cookies()}
            sid = cookies.get("sid")
            xsrf = cookies.get("XSRF-TOKEN")
            if not sid or not xsrf:
                raise RuntimeError("Cambium login did not yield sid/XSRF-TOKEN cookies")
            return {"sid": sid, "xsrf": xsrf}
        finally:
            browser.close()


class CambiumController:
    name = "Cambium"

    def __init__(self, base_urls: list[str], email: str, password: str) -> None:
        self.base_urls = base_urls
        self.email = email
        self.password = password

    def _list_devices_for_site(self, base_url: str) -> list[dict]:
        base_url = base_url.rstrip("/")
        devices_url = f"{base_url}/tree/devices"
        site_name = _site_name(base_url)
        auth = _login_and_get_cookies(LOGIN_URL, devices_url, site_name, self.email, self.password)
        headers = {
            "Cookie": f"sid={auth['sid']}; XSRF-TOKEN={auth['xsrf']}",
            "X-XSRF-TOKEN": auth["xsrf"],
        }

        all_devices: list[dict] = []
        offset = 0
        while True:
            resp = requests.get(
                devices_url,
                params={"offset": offset, "limit": PAGE_LIMIT},
                headers=headers,
                verify=False,
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            data = body.get("data") or {}
            batch = data.get("devices") or []
            all_devices.extend(batch)

            total_count = (data.get("_metadata") or {}).get("totalCount", len(all_devices))
            if len(all_devices) >= total_count or not batch:
                break
            # The API silently caps its actual page size below the requested `limit`
            # (observed: 100 regardless of a 200 limit) — advancing by the requested
            # size instead of len(batch) skips every device in between.
            offset += len(batch)

        return all_devices

    def _list_devices_for_site_safe(self, base_url: str) -> list[dict]:
        try:
            return self._list_devices_for_site(base_url)
        except Exception as e:  # noqa: BLE001 - Playwright/HTTP failures must not crash the run
            logger.error("Cambium: site %r failed: %s", base_url, e)
            return []

    def list_devices(self) -> list[ControllerDevice]:
        devices: list[ControllerDevice] = []
        # Each site is an independent Playwright login + device fetch, so multiple
        # configured sites run concurrently rather than paying a full login+fetch
        # cycle (Chromium cold-start plus several seconds of fixed waits) one at a
        # time for what CAMBIUM_BASE_URL already treats as a purely additive config.
        with ThreadPoolExecutor(max_workers=max(1, len(self.base_urls))) as executor:
            per_site_devices = executor.map(self._list_devices_for_site_safe, self.base_urls)
            for raw_devices in per_site_devices:
                for d in raw_devices:
                    cfg = d.get("cfg") or {}
                    net = d.get("net") or {}
                    devices.append(
                        ControllerDevice(
                            controller=self.name,
                            name=cfg.get("name") or d.get("name") or "",
                            ip=net.get("wan") or net.get("ip") or "",
                            mac=(d.get("mac") or "").lower(),
                            serial=d.get("sn") or "",
                            device_id=(d.get("mac") or "").lower(),
                        )
                    )
        logger.info("Cambium: collected %d device(s) total", len(devices))
        return devices
