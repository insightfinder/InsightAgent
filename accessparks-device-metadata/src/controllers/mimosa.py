"""Mimosa controller — Mimosa Cloud (cloud.mimosa.co).

Ported from InsightAgent/Mimosa/getmessages_mimosa.py (mimosa_login,
query_mimosa_metrics's device-listing loop). network_id is a static config
value here too — Mimosa exposes no networks-listing endpoint to discover it.

Deliberate fix over the reference: its HTTP-200 login branch reads an
undefined `location` variable (a NameError bug in the original), so success
there is handled directly here instead of copied.
"""

from __future__ import annotations

import logging

import requests

from models import ControllerDevice

logger = logging.getLogger(__name__)

PAGE_SIZE = 1000


class MimosaController:
    name = "Mimosa"

    def __init__(self, base_url: str, username: str, password: str, network_id: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.network_id = network_id

    def _login(self) -> requests.Session:
        session = requests.Session()
        welcome_url = f"{self.base_url}/app/welcome.html"
        session.get(welcome_url, verify=False, timeout=10).raise_for_status()

        resp = session.post(
            f"{self.base_url}/login/j_spring_security_check",
            data={"j_username": self.username, "j_password": self.password},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Referer": welcome_url,
            },
            verify=False,
            timeout=10,
            allow_redirects=False,
        )

        if resp.status_code == 200:
            # Spring Security normally redirects on both success and failure — a
            # bare 200 here is atypical, and could mean the login form was
            # re-rendered with bad credentials rather than a genuine success page.
            # A re-rendered form still contains its own j_username input field, so
            # treat that as a login failure rather than trusting the status alone.
            if "j_username" in resp.text:
                raise RuntimeError("Mimosa login failed: login form was re-rendered (bad credentials?)")
            return session
        if resp.status_code in (302, 303):
            location = resp.headers.get("Location", "")
            if "app/index.html" in location and "error" not in location.lower():
                return session
            raise RuntimeError(f"Mimosa login failed: redirected to {location!r}")
        raise RuntimeError(f"Mimosa login failed with status {resp.status_code}")

    def list_devices(self) -> list[ControllerDevice]:
        session = self._login()

        all_devices: list[dict] = []
        page = 0
        while True:
            resp = session.get(
                f"{self.base_url}/{self.network_id}/devices/",
                params={"pageNumber": page, "pageSize": PAGE_SIZE},
                verify=False,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content") or []
            if not content:
                break
            all_devices.extend(content)
            if data.get("last", True):
                break
            page += 1

        devices: list[ControllerDevice] = []
        for d in all_devices:
            devices.append(
                ControllerDevice(
                    controller=self.name,
                    name=d.get("friendlyName") or "",
                    ip=d.get("ipAddress") or "",
                    mac=(d.get("macAddress") or "").lower(),
                    serial=d.get("serialNumber") or "",
                    device_id=str(d.get("id") or ""),
                )
            )
        logger.info("Mimosa: collected %d device(s) total", len(devices))
        return devices
