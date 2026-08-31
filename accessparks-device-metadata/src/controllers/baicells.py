"""Baicells controller — CloudCore northbound API.

Ported from InsightAgent/baicells-agent/baicells_client.py: token login,
group-hierarchy traversal (only integer-id/leaf groups are queryable), and
per-group paginated device queries. List rows are snake_case (host_name,
mac_address, serial_number); IP is not on the list at all and requires a
per-device GET /cpe/infos/{serial} call (camelCase response).

CloudCore allows 20 requests/min account-wide. IP enrichment is cached to
disk (serial -> {ip, fetched_at}) and capped by a wall-clock budget per run,
so a large fleet fills in over several hourly runs instead of blocking one
run for N/20 minutes. Devices left unenriched this run keep ip="" and are
logged, never guessed.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import requests

from controllers.ratelimit import RateLimiter
from models import ControllerDevice

logger = logging.getLogger(__name__)

RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_PERIOD = 60.0
DEFAULT_ENRICH_BUDGET_SECONDS = 900
CACHE_PATH = Path(__file__).parent.parent.parent / ".cache" / "baicells_ips.json"


def _load_cache() -> dict[str, dict]:
    try:
        text = CACHE_PATH.read_text()
    except FileNotFoundError:
        return {}
    try:
        return json.loads(text)
    except ValueError:
        # A crash mid-write (plausible on a cron box also running Cambium's
        # Chromium subprocess) can leave a truncated file — that's real
        # corruption, not "no cache yet", and losing the accumulated
        # enrichment progress silently is exactly the kind of gap this
        # module's budget/cache design exists to avoid.
        logger.warning("Baicells: IP cache at %s is corrupt — starting fresh", CACHE_PATH)
        return {}


def _save_cache(cache: dict[str, dict]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CACHE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(cache))
    os.replace(tmp_path, CACHE_PATH)


class BaicellsController:
    name = "Baicells"

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        enrich_budget_seconds: int = DEFAULT_ENRICH_BUDGET_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.enrich_budget_seconds = enrich_budget_seconds
        self.limiter = RateLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_PERIOD)
        self._token: str | None = None

    def _login(self) -> str:
        self.limiter.acquire()
        resp = requests.post(
            f"{self.base_url}/northboundApi/v1/access/token",
            json={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/json;charset=UTF-8"},
            verify=False,
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") not in (0, 200):
            raise RuntimeError(f"Baicells login failed: {body.get('message')}")
        token = body.get("data", {}).get("token")
        if not token:
            raise RuntimeError("Baicells login succeeded but response had no token")
        return token

    def _call(self, method: str, path: str, **kwargs) -> dict:
        if self._token is None:
            self._token = self._login()

        for attempt in (1, 2):
            self.limiter.acquire()
            resp = requests.request(
                method,
                f"{self.base_url}{path}",
                headers={"Authorization": self._token, "Content-Type": "application/json;charset=UTF-8"},
                verify=False,
                timeout=15,
                **kwargs,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") in (0, 200):
                return body

            message = body.get("message") or ""
            lowered = message.lower()
            # Wording for an expired/invalidated token isn't confirmed against a
            # real expiry from this vendor (only ever seen bad-credential login
            # errors live) — cast a slightly wider net than a single exact phrase
            # so a differently-worded expiry still triggers a refresh-and-retry
            # instead of a hard failure for that call.
            token_expired = "token" in lowered and any(kw in lowered for kw in ("invalid", "expired", "unauthorized"))
            if attempt == 1 and token_expired:
                self._token = self._login()
                continue
            raise RuntimeError(f"Baicells API error: {message}")

        raise AssertionError("unreachable")

    def _flatten_groups(self, groups: list[dict], result: list[dict]) -> None:
        for g in groups:
            result.append(g)
            children = g.get("children") or []
            if children:
                self._flatten_groups(children, result)

    def _get_queryable_group_ids(self) -> list[int]:
        body = self._call("GET", "/northboundApi/v1/device/group")
        rows = body.get("data", {}).get("rows", [])
        flat: list[dict] = []
        self._flatten_groups(rows, flat)
        return [g["id"] for g in flat if isinstance(g.get("id"), int)]

    def _get_devices_for_group(self, group_id: int, page_size: int = 100) -> list[dict]:
        all_devices: list[dict] = []
        page_no = 0
        while True:
            body = self._call(
                "POST",
                "/northboundApi/v1/device/query",
                json={
                    "isGnb": 0,
                    "groupId": group_id,
                    "searchText": None,
                    "pageSize": page_size,
                    "pageNo": page_no,
                },
            )
            result = body.get("data", {})
            devices = result.get("rows", [])
            total = result.get("total", 0)
            all_devices.extend(devices)
            if len(all_devices) >= total or not devices:
                break
            page_no += 1
        return all_devices

    def _get_cpe_ip(self, serial_number: str) -> str:
        body = self._call("GET", f"/northboundApi/v1/cpe/infos/{serial_number}")
        ip = (body.get("data") or {}).get("ipAddress") or ""
        return "" if ip == "0.0.0.0" else ip

    def _enrich_ips(self, serials: list[str]) -> dict[str, str]:
        cache = _load_cache()
        now = time.time()

        uncached = [s for s in serials if s not in cache]
        cached_sorted_by_age = sorted(
            (s for s in serials if s in cache), key=lambda s: cache[s].get("fetched_at", 0)
        )
        queue = uncached + cached_sorted_by_age

        deadline = now + self.enrich_budget_seconds
        refreshed = 0
        for serial in queue:
            if time.time() >= deadline:
                break
            try:
                ip = self._get_cpe_ip(serial)
            except (requests.exceptions.RequestException, RuntimeError) as e:
                logger.warning("Baicells: IP fetch failed for %s: %s", serial, e)
                continue
            cache[serial] = {"ip": ip, "fetched_at": time.time()}
            refreshed += 1

        skipped = len(queue) - refreshed
        if skipped:
            logger.warning(
                "Baicells: %d device(s) left with cached/empty IP this run"
                " (budget exhausted or per-device fetch failed — will retry next run)",
                skipped,
            )
        _save_cache(cache)
        return {s: cache[s]["ip"] for s in serials if s in cache}

    def list_devices(self) -> list[ControllerDevice]:
        group_ids = self._get_queryable_group_ids()
        logger.info("Baicells: found %d queryable group(s)", len(group_ids))

        all_devices: list[dict] = []
        for group_id in group_ids:
            try:
                all_devices.extend(self._get_devices_for_group(group_id))
            except (requests.exceptions.RequestException, RuntimeError) as e:
                logger.warning("Baicells: device query failed for group %s: %s", group_id, e)

        serials = [d.get("serial_number") for d in all_devices if d.get("serial_number")]
        ip_by_serial = self._enrich_ips(serials)

        devices: list[ControllerDevice] = []
        for d in all_devices:
            serial = d.get("serial_number") or ""
            devices.append(
                ControllerDevice(
                    controller=self.name,
                    name=d.get("host_name") or "",
                    ip=ip_by_serial.get(serial, ""),
                    mac=(d.get("mac_address") or "").upper(),
                    serial=serial,
                    device_id=serial,
                )
            )
        logger.info("Baicells: collected %d device(s) total", len(devices))
        return devices
