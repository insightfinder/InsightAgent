#!/usr/bin/env python3
"""
Asset cache client — eNB/CPE asset lookup via the AccessParks asset-cache server.

The asset-cache server mirrors Jira Assets device data and exposes a simple REST
lookup API (GET /devices?ip=...&serial=...), removing the need to talk to Jira's
AQL API (workspace discovery, attribute-id discovery, pagination) directly. See
CLAUDE.md for the server's URL/auth and the field mapping this module relies on.

Matching strategy (in priority order) — unchanged from the direct-Jira version,
now applied to asset-cache device records instead of Jira AQL objectEntries:
  eNBs:
    1. device_name numeric suffix — e.g. asset device_name="eNodeB200" → device_id "200"
                                      Stable even if IP changes.
    2. ip_address                  — falls back to IP for assets whose device_name has no
                                      embedded device ID (e.g. "eNB", "RoofeNodeB").
  CPEs:
    1. serial_number                — the CPE's serial number matched against the asset's
                                       serial_number field. Serial search is case-sensitive
                                       (uppercase) — callers must pass already-uppercased
                                       serials (see get_cli_metrics.py's parse_cpe_kpi(),
                                       the single point of capture).
    2. ip_address (WAN IP fallback) — tried only when serial doesn't match (see
                                       build_asset_map._resolve_map_by_serial's
                                       ip_fallback_map). Weaker than serial: WAN IPs are
                                       DHCP'd/NAT'd and can be shared or stale.
"""

from __future__ import annotations

import inspect
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_DIGITS_RE = re.compile(r"\d+$")
ENB_NAME_RE = re.compile(r"(eNodeB|eNB)", re.IGNORECASE)

_MAX_WORKERS = 8

_session: requests.Session | None = None
_session_lock = threading.Lock()


def _get_session(api_key: str) -> requests.Session:
    """Return a process-wide requests.Session, built once and reused across calls.

    fetch_assets() is called once per tick from send_metrics.py's long-running loop —
    a fresh Session per call would pay TCP/TLS setup every tick instead of reusing a
    warm connection pool. Retry/backoff mirrors insightfinder._build_session(), widened
    to GET since every request this module makes is a GET.
    """
    global _session
    with _session_lock:
        if _session is None:
            s = requests.Session()
            # Retry()'s accepted kwargs vary across urllib3 versions (mirrors
            # insightfinder._build_session() — see that function's comment).
            supported = inspect.signature(Retry.__init__).parameters
            retry_kwargs = dict(
                total=3,
                connect=3,
                read=3,
                status=3,
                backoff_factor=1.0,
                backoff_jitter=0.3,
                status_forcelist=(429, 500, 502, 503, 504),
                respect_retry_after_header=True,
                raise_on_status=False,
            )
            if "allowed_methods" in supported:
                retry_kwargs["allowed_methods"] = ("GET",)
            elif "method_whitelist" in supported:
                retry_kwargs["method_whitelist"] = ("GET",)
            retry_kwargs = {k: v for k, v in retry_kwargs.items() if k in supported}
            retry = Retry(**retry_kwargs)
            adapter = HTTPAdapter(max_retries=retry)
            s.mount("http://", adapter)
            s.mount("https://", adapter)
            _session = s
        _session.headers.update({"X-API-Key": api_key, "Accept": "application/json"})
        return _session


def _get_device(session: requests.Session, base_url: str, param: str, value: str) -> list[dict]:
    resp = session.get(f"{base_url.rstrip('/')}/devices", params={param: value}, timeout=30)
    resp.raise_for_status()
    devices = resp.json()
    if not isinstance(devices, list):
        raise ValueError(f"expected a list response, got {type(devices).__name__}")
    return devices


def _first_token(name: str) -> str:
    """Return only the leading whitespace-delimited token of a Jira asset name.

    Asset names sometimes carry a trailing note or a MAC address appended by the
    object's naming pattern (e.g. "DVR-ResPEC44 is this PEC104 or PEC40 or TS44-ue" or
    "DVR-?h-ue 6C:AD:EF:15:B1:B9") — only the first token is the actual device name, the
    rest is dropped. Splits on whitespace only, so hyphens stay part of the token.
    Empty/whitespace-only input returns "" (handled by downstream blank-label guards).
    """
    parts = name.split()
    return parts[0] if parts else ""


def _to_asset(obj: dict) -> dict:
    """Map an asset-cache device record to the
    {label, ip, device_id_hint, serial, mac, object_key, venue, component_name} shape.

    - label: the first whitespace-delimited token of the device's asset name (e.g.
      "Tus-TennisCourt-eNodeB200"), trimming any trailing note/MAC — see _first_token()
    - ip: ip_address value, or "" if unset
    - device_id_hint: trailing digits from device_name (e.g. "200"), or "" if none
    - serial: serial_number value, or "" if unset
    - mac: mac_address value, or "" if unset — used for the MAC-first instance identifier
    - object_key: object_key value (Jira key, e.g. "IHS-35111"), or "" if unset
    - venue: meta.venue value, or "" if unset — used as the reported zone
    - component_name: "{manufacturer}-{device_class}" (each defaulting to "NONE" if
      unset), same formula as the zabbix/netexperience agents; "" if both are unset
      (NONE-NONE), so callers can fall back to their own static component name
    """
    label = _first_token(obj.get("name") or "")
    ip = obj.get("ip_address") or ""
    device_name = obj.get("device_name") or ""
    m = _DIGITS_RE.search(device_name)
    device_id_hint = m.group() if m else ""
    serial = obj.get("serial_number") or ""
    mac = obj.get("mac_address") or ""
    object_key = obj.get("object_key") or ""
    meta = obj.get("meta") or {}
    model = obj.get("model") or {}
    venue = meta.get("venue") or ""
    manufacturer = model.get("manufacturer") or meta.get("manufacturer") or "NONE"
    device_class = model.get("device_class") or "NONE"
    component_name = f"{manufacturer}-{device_class}"
    if component_name == "NONE-NONE":
        component_name = ""
    return {
        "label": label,
        "ip": ip,
        "device_id_hint": device_id_hint,
        "serial": serial,
        "mac": mac,
        "object_key": object_key,
        "venue": venue,
        "component_name": component_name,
    }


def fetch_assets(
    base_url: str,
    api_key: str,
    ips: list[str] | None = None,
    serials: list[str] | None = None,
) -> list[dict]:
    """Return asset dicts for all cache-server devices matching the given IPs and/or serials.

    Each dict: {label, ip, device_id_hint, serial} — see _to_asset() for field mapping.

    One GET /devices?ip=<v> (or ?serial=<v>) request per value, run concurrently via a
    bounded thread pool so a large CPE serial set doesn't serialize tick latency (mirrors
    the ThreadPoolExecutor pattern in get_metrics.collect_metrics). Passing only ips or
    only serials is fine; passing neither returns [] without any HTTP calls.

    Raises if every request failed (the asset cache is unreachable/down) so callers can
    distinguish "no assets matched" from "couldn't ask" — send_metrics.refresh_jira_mappings()
    relies on this to skip resolution (and its 1-hour unmapped cooldown) on a real outage
    rather than treating every candidate as confirmed-unmapped. A partial failure (some
    requests succeed) does not raise — the failed values are simply absent from the result
    and are naturally retried next tick.

    Results are deduplicated by their resolved (label, ip, serial) content, since the same
    device could otherwise appear twice (matched by ip in one request and, in principle,
    by serial in another).
    """
    ips = [ip for ip in (ips or []) if ip]
    serials = [s for s in (serials or []) if s]
    if not ips and not serials:
        return []

    session = _get_session(api_key)

    requests_to_make = [("ip", ip) for ip in ips] + [("serial", s) for s in serials]
    seen_keys: set[tuple[str, str, str]] = set()
    results: list[dict] = []
    failures = 0

    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(requests_to_make))) as pool:
        futures = {
            pool.submit(_get_device, session, base_url, param, value): (param, value)
            for param, value in requests_to_make
        }
        for future in as_completed(futures):
            param, value = futures[future]
            try:
                devices = future.result()
            except Exception as e:
                logger.warning(f"Asset cache lookup failed for {param}={value}: {e}")
                failures += 1
                continue
            for obj in devices:
                asset = _to_asset(obj)
                dedup_key = (asset["label"], asset["ip"], asset["serial"])
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                results.append(asset)

    if failures and failures == len(requests_to_make):
        raise RuntimeError(f"Asset cache unreachable: all {failures} lookup(s) failed")

    logger.info(f"Fetched {len(results)} asset(s) for the queried IP(s)/serial(s)")
    return results
