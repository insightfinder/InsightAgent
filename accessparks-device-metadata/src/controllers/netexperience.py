"""NetExperience controller — CMAP portal REST API.

Ported from InsightAgent/netexperience-agent (netexperience/util.go). Three
chained calls: list customers scoped to our service provider, list equipment
per customer (cursor-paginated), then a per-equipment status call for IP
(not present on the equipment list itself). Shares the 180 req/10s quota
across all three call types via one RateLimiter.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

import requests

from controllers.ratelimit import RateLimiter
from models import ControllerDevice

logger = logging.getLogger(__name__)

RATE_LIMIT_REQUESTS = 180
RATE_LIMIT_PERIOD = 10.0
# Per-request latency to this API (~1s) is the real bottleneck, not the rate limit
# itself — sequential fetching would leave the 180 req/10s budget almost entirely
# unused. This many in-flight requests keeps the limiter, not latency, as the cap.
CONCURRENCY = 20


class NetExperienceController:
    name = "NetExperience"

    def __init__(
        self,
        base_url: str,
        user_id: str,
        password: str,
        service_provider_id: int,
        fetch_ip: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.password = password
        self.service_provider_id = service_provider_id
        self.fetch_ip = fetch_ip
        self.limiter = RateLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_PERIOD)

    def _login(self) -> str:
        self.limiter.acquire()
        resp = requests.post(
            f"{self.base_url}/management/cmap/oauth2/token",
            json={"userId": self.user_id, "password": self.password},
            verify=False,
            timeout=15,
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise RuntimeError("NetExperience login succeeded but response had no access_token")
        return token

    def _get(self, token: str, path: str, params: dict) -> requests.Response:
        self.limiter.acquire()
        resp = requests.get(
            f"{self.base_url}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            verify=False,
            timeout=30,
        )
        resp.raise_for_status()
        return resp

    def _list_customers(self, token: str) -> list[dict]:
        resp = self._get(
            token,
            "/portal/cmap/customer/forSp",
            {"serviceProviderId": self.service_provider_id, "name": "", "operationalState": ""},
        )
        return resp.json()

    def _list_equipment(self, token: str, customer_id: int) -> list[dict]:
        equipment: list[dict] = []
        pagination_context = None
        while True:
            params = {"customerId": customer_id}
            if pagination_context is not None:
                # Must be a single JSON-encoded string value, matching what the API
                # itself returns as `context` — handing requests a raw dict here
                # instead makes it iterate the dict's keys into repeated
                # paginationContext=<key> params (silently dropping every page
                # past the first for any customer with more than one page).
                params["paginationContext"] = json.dumps(
                    {
                        "model_type": "PaginationContext",
                        "cursor": pagination_context.get("cursor"),
                        "lastPage": pagination_context.get("lastPage", False),
                        "lastReturnedPageNumber": pagination_context.get("lastReturnedPageNumber"),
                        "maxItemsPerPage": pagination_context.get("maxItemsPerPage"),
                        "totalItemsReturned": pagination_context.get("totalItemsReturned"),
                    }
                )
            try:
                resp = self._get(token, "/portal/equipment/forCustomer", params)
            except requests.exceptions.RequestException as e:
                # A failure on page N+1 must not discard the N pages already fetched
                # for this customer.
                logger.warning(
                    "NetExperience: equipment page fetch failed for customer %s after %d item(s): %s",
                    customer_id, len(equipment), e,
                )
                break
            data = resp.json()
            items = data.get("items") or []
            equipment.extend(items)

            context = data.get("context") or {}
            if context.get("lastPage") or context.get("totalItemsReturned", 0) < context.get(
                "maxItemsPerPage", 1
            ):
                break
            pagination_context = context

        return equipment

    def _get_ip(self, token: str, customer_id: int, equipment_id: int) -> str:
        resp = self._get(
            token,
            "/portal/status/forEquipment",
            {"customerId": customer_id, "equipmentId": equipment_id},
        )
        statuses = resp.json()
        if not isinstance(statuses, list):
            return ""
        for status in statuses:
            if status.get("statusDataType") == "PROTOCOL":
                ip = (status.get("details") or {}).get("reportedIpV4Addr")
                if ip:
                    return ip
        return ""

    def _fetch_equipment_for_customer(self, token: str, customer: dict) -> list[dict]:
        customer_id = customer.get("id")
        if customer_id is None:
            return []
        try:
            return self._list_equipment(token, customer_id)
        except requests.exceptions.RequestException as e:
            logger.warning("NetExperience: equipment fetch failed for customer %s: %s", customer_id, e)
            return []

    def _fetch_ip_for_equipment(self, token: str, eq: dict) -> str:
        customer_id = eq.get("customerId")
        equipment_id = eq.get("id")
        if customer_id is None or equipment_id is None:
            return ""
        try:
            return self._get_ip(token, customer_id, equipment_id)
        except requests.exceptions.RequestException as e:
            logger.warning("NetExperience: IP fetch failed for equipment %s: %s", equipment_id, e)
            return ""

    def list_devices(self) -> list[ControllerDevice]:
        token = self._login()
        customers = self._list_customers(token)
        logger.info("NetExperience: found %d customer(s)", len(customers))

        all_equipment: list[dict] = []
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
            for equipment in executor.map(lambda c: self._fetch_equipment_for_customer(token, c), customers):
                all_equipment.extend(equipment)

        ips: list[str] = [""] * len(all_equipment)
        if self.fetch_ip:
            with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
                ips = list(executor.map(lambda eq: self._fetch_ip_for_equipment(token, eq), all_equipment))

        devices: list[ControllerDevice] = []
        for eq, ip in zip(all_equipment, ips):
            devices.append(
                ControllerDevice(
                    controller=self.name,
                    name=eq.get("name") or "",
                    ip=ip,
                    mac=((eq.get("baseMacAddress") or {}).get("addressAsString") or "").upper(),
                    serial=eq.get("serial") or "",
                    device_id=str(eq.get("id") or ""),
                )
            )
        logger.info("NetExperience: collected %d device(s) total", len(devices))
        return devices
