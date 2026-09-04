"""Tarana controller — Tarana Cloud Suite (TCS) REST API.

Ported from InsightAgent/tarana-agent/tarana/tarana.go (login, GetDevices).
region_ids defaults to the known-good set from the deployed accessParks-tarana
metrics agent's config.yaml (region_ids: [33, 1203, 1202]) via TARANA_REGION_IDS.
Runtime discovery (used only if TARANA_REGION_IDS is left blank) has been
verified to surface region 33 but not 1203/1202 for this account — so leaving
it blank risks silently under-collecting relative to the known-good set.

Region discovery is NOT GET /api/nqs/v1/regions — that 404s. It's
GET /api/nqs/v1/operators/{operatorId}/regions, where operatorId is the
`custom:operatorId` claim baked into the login response's idToken (a JWT;
decoded here without signature verification since it's our own just-issued
token, only for reading a claim). Verified live: operatorId 27 ->
region 33 ("AccessParks") -> devices/search with ids:[33] returns real
device rows. The device-search response includes macAddress (contrary to the
tarana.go Device struct's field list) — already colon-separated uppercase,
verified live against the deployed regions, and mapped here so Tarana
devices can be matched to Jira/Zabbix by MAC like every other vendor's.
"""

from __future__ import annotations

import base64
import json
import logging

import requests

from models import ControllerDevice

logger = logging.getLogger(__name__)


def _decode_jwt_claims(token: str) -> dict:
    payload = token.split(".")[1]
    padded = payload + "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


class TaranaController:
    name = "Tarana"

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        region_ids: list[int] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.region_ids = region_ids

    def _login(self) -> dict[str, str]:
        resp = requests.post(
            f"{self.base_url}/api/tcs/v1/user-auth/login",
            auth=(self.username, self.password),
            verify=False,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        id_token = data.get("idToken")
        access_token = data.get("accessToken")
        if not id_token or not access_token:
            raise RuntimeError("Tarana login succeeded but response had no idToken/accessToken")
        operator_id = _decode_jwt_claims(id_token).get("custom:operatorId")
        if not operator_id:
            raise RuntimeError("Tarana idToken had no custom:operatorId claim")
        return {"idToken": id_token, "accessToken": access_token, "operatorId": operator_id}

    def _discover_regions(self, cookies: dict[str, str]) -> list[int]:
        resp = requests.get(
            f"{self.base_url}/api/nqs/v1/operators/{cookies['operatorId']}/regions",
            headers={"Cookie": f"idToken={cookies['idToken']}; accessToken={cookies['accessToken']}"},
            verify=False,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        regions = data.get("items") or data.get("regions") or []
        ids = [r["id"] for r in regions if "id" in r]
        if not ids:
            raise RuntimeError(
                "Tarana region discovery returned no regions — set TARANA_REGION_IDS explicitly"
            )
        return ids

    def list_devices(self) -> list[ControllerDevice]:
        cookies = self._login()
        region_ids = self.region_ids or self._discover_regions(cookies)
        logger.info("Tarana: querying region(s) %s", region_ids)

        all_devices: list[dict] = []
        offset = 0
        count = 5000
        while True:
            resp = requests.post(
                f"{self.base_url}/api/nqs/v1/regions/devices/search",
                params={"offset": offset, "count": count},
                json={"ids": region_ids, "deviceFilter": {}},
                headers={
                    "Cookie": f"idToken={cookies['idToken']}; accessToken={cookies['accessToken']}",
                    "Content-Type": "application/json",
                },
                verify=False,
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("error"):
                raise RuntimeError(f"Tarana device search API error: {body['error']}")
            data = body.get("data") or {}
            items = data.get("items") or []
            all_devices.extend(items)

            total_count = data.get("totalCount", len(all_devices))
            if len(all_devices) >= total_count or not items:
                break
            # Advance by the actual batch length, not the requested count — the
            # structurally identical Cambium endpoint was confirmed to silently cap
            # its real page size below whatever was requested, and advancing by the
            # requested size there silently skipped every other page.
            offset += len(items)

        devices: list[ControllerDevice] = []
        for d in all_devices:
            devices.append(
                ControllerDevice(
                    controller=self.name,
                    name=d.get("hostName") or "",
                    ip=d.get("ip") or "",
                    mac=(d.get("macAddress") or "").upper(),
                    serial=d.get("serialNumber") or "",
                    device_id=d.get("serialNumber") or "",
                )
            )
        logger.info("Tarana: collected %d device(s) total", len(devices))
        return devices
