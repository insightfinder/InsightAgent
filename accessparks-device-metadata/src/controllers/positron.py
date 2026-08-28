"""Positron controller — GAM headend units + CPE endpoints over HTTPS Basic
Auth. Reached through the same SSH tunnel as Zabbix (see
scripts/zabbix-tunnel.sh and POSITRON_TUNNEL_* in .env) — 192.168.102.16 is
on the same internal subnet as the Zabbix host (192.168.102.31), so it rides
that one tunnel instead of needing a second SSH connection.

Ported from InsightAgent/positron-agent (positron/positron.go, positron/util.go)
— GetEndpoints + GetDevices only; this agent doesn't ingest Positron's
metrics/alarms. Endpoints (`/api/v1/endpoint/list/all`) are CPEs; devices
(`/api/v1/device/list`) are GAM headend units — two distinct populations
(different id space), not duplicates of each other. Deliberately faithful to
the reference's odd contract for `/device/list`: its paging/filter params
are sent as HTTP headers, not query params or a body — that's what the API
expects.
"""

from __future__ import annotations

import logging
import re

import requests

from models import ControllerDevice

logger = logging.getLogger(__name__)

_BARE_NUMBER_RE = re.compile(r"^[0-9]+$")


def _looks_like_name(s: str) -> bool:
    s = (s or "").strip()
    return bool(s) and not _BARE_NUMBER_RE.match(s)


def _endpoint_own_name(rec: dict) -> str:
    # confEndpointName holds the assigned hostname for the large majority of
    # endpoints; confUserName is a fallback for the rest, where
    # confEndpointName is either empty or has degraded to a bare port/slot
    # number (e.g. "10105") rather than a real name.
    conf_endpoint_name = rec.get("confEndpointName") or ""
    conf_user_name = rec.get("confUserName") or ""
    if _looks_like_name(conf_endpoint_name):
        return conf_endpoint_name
    if _looks_like_name(conf_user_name):
        return conf_user_name
    return conf_endpoint_name


class PositronController:
    name = "Positron"

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth = (username, password)

    def _get_endpoints(self) -> list[dict]:
        resp = requests.get(
            f"{self.base_url}/api/v1/endpoint/list/all",
            auth=self.auth,
            verify=False,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("data") or []

    def _get_devices(self) -> list[dict]:
        resp = requests.get(
            f"{self.base_url}/api/v1/device/list",
            auth=self.auth,
            headers={
                "filter": "",
                "mode": "auto",
                "pageNo": "0",
                "pageSize": "5000",
                "param": "",
                "sessionId": "123",
                "sortBy": "",
                "sortDir": "",
            },
            verify=False,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("data") or []

    def list_devices(self) -> list[ControllerDevice]:
        devices: list[ControllerDevice] = []

        for rec in self._get_endpoints():
            devices.append(
                ControllerDevice(
                    controller=self.name,
                    name=_endpoint_own_name(rec),
                    ip="",  # endpoints report no IP of their own
                    mac=(rec.get("macAddress") or "").lower(),
                    serial=rec.get("serialNumber") or "",
                )
            )

        for rec in self._get_devices():
            ip = rec.get("ipAddress") or ""
            if ip == "0.0.0.0":  # unset/unreachable placeholder
                ip = ""
            devices.append(
                ControllerDevice(
                    controller=self.name,
                    name=rec.get("name") or "",
                    ip=ip,
                    mac="",  # devices (GAM headend units) report no MAC
                    serial=rec.get("serialNumber") or "",
                )
            )

        logger.info("Positron: collected %d device(s) total", len(devices))
        return devices
