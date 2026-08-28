"""Zabbix host resolution.

This AccessParks Zabbix instance has ~31,000 hosts (multi-tenant, not just
AccessParks devices). Two things follow from that scale:

- Name/IP matching: Zabbix has no server-side IP filter and its host-name
  filter is exact-match only, so (as every existing AccessParks agent does,
  e.g. zabbix-ap/device_inventory_lookup.py) we fetch the full host set once
  with host.get and match in Python.
- Tag matching: combining `selectTags` with the bulk host.get above 500s on
  this server, and even batching a separate `hostids`-scoped selectTags call
  across all 31k hosts drops the connection partway through (confirmed by
  hand against this deployment). Zabbix's `tags` filter parameter lets the
  server do that lookup directly instead — `host.get` with
  `{"tags": [{"tag": "jira_device_key", "value": ..., "operator": 1}]}` — so
  the jira_device_key match below is one small per-device query rather than
  a bulk tag dump.
"""

from __future__ import annotations

import logging

import requests
from pyzabbix import ZabbixAPI
from pyzabbix import ZabbixAPIException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from models import ZabbixMatch

# Connection-level failures (tunnel down, refused, timed out) surface as
# requests exceptions, not ZabbixAPIException — both must abort the run with
# a clean message rather than a raw traceback.
ZABBIX_ERRORS = (ZabbixAPIException, requests.exceptions.RequestException)

logger = logging.getLogger(__name__)

JIRA_KEY_TAG = "jira_device_key"


class ZabbixIndex:
    def __init__(self, zapi: ZabbixAPI) -> None:
        self._zapi = zapi
        self.by_hostid: dict[str, dict] = {}
        # A value of None means the key is ambiguous (two+ hosts share it) and
        # must never be used to match — on a ~31k-host multi-tenant instance,
        # picking "whichever host was indexed first" would silently reconcile
        # a device against an unrelated tenant's host.
        self.by_name: dict[str, dict | None] = {}
        self.by_ip: dict[str, dict | None] = {}

    def _index(self, table: dict[str, dict | None], key: str, host: dict) -> None:
        if key not in table:
            table[key] = host
        elif table[key] is not None:
            # Expected at this scale (~31k multi-tenant hosts) to be common
            # for generic names — debug, not warning, to avoid log flooding.
            logger.debug(
                "Ambiguous Zabbix key %r shared by multiple hosts — disabling it as a match key",
                key,
            )
            table[key] = None

    def add(self, host: dict) -> None:
        hostid = host.get("hostid") or ""
        if not hostid:
            return
        self.by_hostid[hostid] = host

        for name_field in ("host", "name"):
            val = (host.get(name_field) or "").strip().lower()
            if val:
                self._index(self.by_name, val, host)

        interfaces = host.get("interfaces") or []
        primary = next(
            (i for i in interfaces if i.get("main") == "1" and i.get("type") == "1"),
            None,
        )
        chosen = primary or next((i for i in interfaces if i.get("ip")), None)
        if chosen and chosen.get("ip"):
            self._index(self.by_ip, chosen["ip"], host)

    def _lookup_by_jira_key(self, jira_object_key: str) -> tuple[dict | None, bool]:
        """Returns (host, had_error) — same tri-state contract as
        JiraAssetClient.find_device: an error is never returned as a plain
        miss, so a transient blip on this per-device RPC can't be misread by
        resolve() as "confirmed absent from Zabbix"."""
        try:
            result = self._zapi.do_request(
                "host.get",
                {
                    "output": ["hostid", "host", "name"],
                    "tags": [
                        {"tag": JIRA_KEY_TAG, "value": jira_object_key, "operator": 1}
                    ],
                },
            )["result"]
        except ZABBIX_ERRORS as e:
            logger.warning("Zabbix tag lookup failed for %r: %s", jira_object_key, e)
            return None, True
        return (result[0] if result else None), False

    def resolve(
        self,
        *,
        jira_object_key: str,
        jira_zabbix_host_id: str,
        device_name: str,
        device_ip: str,
    ) -> tuple[ZabbixMatch | None, bool]:
        """Priority: jira_device_key tag (server-side, per Jira match) ->
        Jira's recorded zabbix_host_id (only if that hostid still exists in
        Zabbix) -> host/name match -> primary-interface IP match.

        Returns (match, had_error). Stops at a tag-lookup error rather than
        falling through to the weaker local-index matchers below, so a
        network blip on the primary match method is never reported as a
        confirmed "missing from Zabbix" (see tri-state contract in README.md).
        """
        if jira_object_key:
            host, had_error = self._lookup_by_jira_key(jira_object_key)
            if had_error:
                return None, True
            if host:
                return ZabbixMatch(hostid=host["hostid"], matched_by="jira_device_key"), False

        if jira_zabbix_host_id and jira_zabbix_host_id in self.by_hostid:
            return (
                ZabbixMatch(hostid=jira_zabbix_host_id, matched_by="jira_zabbix_host_id"),
                False,
            )

        name_key = (device_name or "").strip().lower()
        if name_key:
            host = self.by_name.get(name_key)
            if host:
                return ZabbixMatch(hostid=host["hostid"], matched_by="name"), False

        if device_ip:
            host = self.by_ip.get(device_ip)
            if host:
                return ZabbixMatch(hostid=host["hostid"], matched_by="ip"), False

        return None, False


def build_index(
    url: str, user: str, password: str, timeout: int = 30, pool_size: int = 20
) -> ZabbixIndex:
    # resolve() issues one host.get per device (see module docstring) from
    # RECONCILE_CONCURRENCY worker threads sharing this single ZabbixAPI
    # instance. requests' default HTTPAdapter pool (size 10) is smaller than
    # that concurrency, so excess connections get opened-and-discarded
    # instead of reused ("Connection pool is full, discarding connection")
    # — expensive per-request TCP/HTTP setup that serializes throughput, and
    # a connection handed back into a full pool right as the far end (the
    # SSH tunnel / Zabbix's keep-alive) closes it races a fresh request onto
    # a dead socket ("Remote end closed connection without response"). Both
    # are addressed by sizing the pool to the real concurrency and retrying
    # host.get, which is a pure read and safe to retry, on connect/read
    # failures.
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("POST",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    zapi = ZabbixAPI(server=url, timeout=timeout, session=session)
    try:
        zapi.login(user=user, password=password)
        logger.info("Connected to Zabbix %s (API %s)", url, zapi.api_version())
    except ZABBIX_ERRORS as e:
        raise RuntimeError(f"Zabbix login failed: {e}") from e

    logger.info(
        "Fetching Zabbix host list (this is a single bulk call across all hosts and can take a while)..."
    )
    try:
        hosts = zapi.do_request(
            "host.get",
            {
                "output": ["hostid", "host", "name", "status"],
                "selectInterfaces": ["ip", "type", "main"],
            },
        )["result"]
    except ZABBIX_ERRORS as e:
        raise RuntimeError(f"Zabbix host.get failed: {e}") from e

    index = ZabbixIndex(zapi)
    for host in hosts:
        index.add(host)
    logger.info("Indexed %d Zabbix host(s)", len(hosts))
    return index
