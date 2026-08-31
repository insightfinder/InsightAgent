"""UISP controller — Ubiquiti UISP/UNMS REST API.

Ported from InsightAgent/uisp-agent/get_metrics.py. A single unpaginated
`GET /devices` call returns every device across every site in one response —
site is just a field (identification.site.name), never a traversal step like
UniFi's per-site loop.

Auth is a static API token sent as the `x-auth-token` header — there is no
`/user/login` call. The reference agent never authenticates with a
username/password; AccessParks' UISP instance issues a long-lived API token
instead (see its account settings), and that's the only credential this
controller accepts.
"""

from __future__ import annotations

import logging

import requests

from models import ControllerDevice

logger = logging.getLogger(__name__)


class UispController:
    name = "UISP"

    def __init__(self, base_url: str, api_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token

    def list_devices(self) -> list[ControllerDevice]:
        resp = requests.get(
            f"{self.base_url}/nms/api/v2.1/devices",
            headers={"x-auth-token": self.api_token},
            verify=False,
            timeout=30,
        )
        resp.raise_for_status()
        raw_devices = resp.json()

        devices: list[ControllerDevice] = []
        for d in raw_devices:
            identification = d.get("identification") or {}
            ip = d.get("ipAddress") or ""
            if "/" in ip:
                ip = ip.split("/")[0]
            devices.append(
                ControllerDevice(
                    controller=self.name,
                    name=identification.get("name") or "",
                    ip=ip,
                    mac=(identification.get("mac") or "").upper(),
                    serial=identification.get("serialNumber") or "",
                    device_id=str(identification.get("id") or ""),
                )
            )
        logger.info("UISP: collected %d device(s) total", len(devices))
        return devices
