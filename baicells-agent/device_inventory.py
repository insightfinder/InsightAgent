#!/usr/bin/env python3

"""
Device Inventory / Asset Registry lookup.

Enriches BaiCells devices with data from the Device Inventory API, keyed by
MAC address, serial number, or device name (first match wins). Same API and
lookup convention used by the mimosa, netexperience, and tarana-gnmic agents,
so the same physical device resolves to the same InsightFinder instance
identity across agents.
"""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

LOOKUP_PATH = "devicelookup.json"
LOOKUP_CONCURRENCY = 20

_PLACEHOLDER_WORDS = {"", "n/a", "na", "none", "null", "unknown", "tbd"}


def _is_placeholder(value: str | None) -> bool:
    """True if the inventory's value is one of its "no data" conventions:
    known placeholder words, or - generically - a value with no letter or
    digit at all ('-', '.', '--', '...', etc.), since a real MAC/serial/IP
    always contains at least one alphanumeric character."""
    if value is None:
        return True
    trimmed = value.strip()
    if trimmed.lower() in _PLACEHOLDER_WORDS:
        return True
    return not any(c.isalnum() for c in trimmed)


def _clean(raw: dict, key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or _is_placeholder(value):
        return ""
    return value.strip()


def normalize_mac(mac: str | None) -> str:
    """Replace ':' with '-', trim leading/trailing '-'. No case conversion -
    the original casing is preserved so the same physical device produces
    the same instance identifier across agents."""
    if not mac:
        return ""
    converted = mac.strip().replace(":", "-").strip("-").strip()
    if not converted or not any(c.isalnum() for c in converted):
        return ""
    return converted


def normalize_serial(serial: str | None) -> str:
    """Trim whitespace and require at least one alphanumeric character. No
    case conversion."""
    if not serial:
        return ""
    trimmed = serial.strip()
    if not trimmed or not any(c.isalnum() for c in trimmed):
        return ""
    return trimmed


def clean_own_name(name: str | None) -> str:
    """Clean the device's own reported name for use as an instance name
    fallback: '_' and ':' both become '-' (unlike the mimosa/tarana agents'
    CleanDeviceName, which maps '_' to '.')."""
    if not name:
        return ""
    cleaned = name.strip().replace("_", "-").replace(":", "-")
    return cleaned.strip("-").strip()


@dataclass
class DeviceInfo:
    serial_number: str = ""
    object_key: str = ""
    mac_address: str = ""
    name: str = ""
    venue: str = ""
    component_name: str = ""
    ip_address: str = ""


@dataclass
class Identifiers:
    mac: str = ""
    serial: str = ""
    name: str = ""


@dataclass
class InventoryConfig:
    api_key: str = ""
    base_url: str = ""
    timeout_sec: float = 5
    max_retry: int = 2
    retry_delay_sec: float = 0.5
    refresh_hours: float = 24

    @classmethod
    def from_env(cls) -> "InventoryConfig":
        return cls(
            api_key=os.getenv("DEVICE_INVENTORY_API_KEY", ""),
            base_url=os.getenv("DEVICE_INVENTORY_BASE_URL", ""),
            timeout_sec=float(os.getenv("DEVICE_INVENTORY_TIMEOUT_SEC", "5")),
            max_retry=int(os.getenv("DEVICE_INVENTORY_MAX_RETRY", "2")),
            retry_delay_sec=int(os.getenv("DEVICE_INVENTORY_RETRY_DELAY_MS", "500"))
            / 1000.0,
            refresh_hours=float(os.getenv("DEVICE_INVENTORY_REFRESH_HOURS", "24")),
        )


def load_device_lookup() -> dict[str, dict]:
    """Load devicelookup.json from disk; returns {} if absent or invalid."""
    if not os.path.exists(LOOKUP_PATH):
        return {}
    try:
        with open(LOOKUP_PATH) as f:
            data = json.load(f)
        logger.info(f"DeviceLookup: loaded {len(data)} entries from disk")
        return data
    except Exception as e:
        logger.warning(f"DeviceLookup: failed to load {LOOKUP_PATH}: {e}")
        return {}


def is_stale(refresh_hours: float) -> bool:
    """True if devicelookup.json is missing or older than refresh_hours."""
    if not os.path.exists(LOOKUP_PATH):
        return True
    age_hours = (time.time() - os.path.getmtime(LOOKUP_PATH)) / 3600
    return age_hours >= refresh_hours


def get_device_info(cache: dict[str, dict], *candidates: str) -> DeviceInfo:
    """Try each candidate key (typically own MAC, then serial, then name)
    and return the first cache hit."""
    for candidate in candidates:
        if not candidate:
            continue
        entry = cache.get(candidate)
        if entry:
            return DeviceInfo(**entry.get("device", {}))
    return DeviceInfo()


def is_resolved(cache: dict[str, dict], *candidates: str) -> bool:
    """True if any of the candidate keys (own MAC/serial/name) already has a
    cache entry. Used to detect devices that have never gone through an
    inventory lookup, independent of whether the cache as a whole is stale -
    a device seen for the first time must be looked up immediately, not only
    once the next scheduled refresh happens to come around."""
    return any(candidate and candidate in cache for candidate in candidates)


def _lookup_by_identifier(
    session: requests.Session, cfg: InventoryConfig, identifier: str
) -> dict | None:
    if not identifier:
        return None
    url = f"{cfg.base_url}/devices/{quote(str(identifier), safe='')}"
    headers = {"X-API-Key": cfg.api_key, "Accept": "application/json"}
    for attempt in range(cfg.max_retry):
        try:
            resp = session.get(url, headers=headers, timeout=cfg.timeout_sec)
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                if attempt < cfg.max_retry - 1:
                    time.sleep(cfg.retry_delay_sec)
                continue
            body = resp.text.strip()
            if not body or body == "null":
                return None
            return resp.json()
        except Exception:
            if attempt < cfg.max_retry - 1:
                time.sleep(cfg.retry_delay_sec)
    return None


def _extract_device_info(raw: dict) -> dict:
    dev = raw.get("device") if isinstance(raw.get("device"), dict) else raw
    meta = dev.get("meta") if isinstance(dev.get("meta"), dict) else {}
    model = dev.get("model") if isinstance(dev.get("model"), dict) else {}

    manufacturer = _clean(model, "manufacturer") or _clean(meta, "manufacturer")
    device_class = _clean(model, "device_class")
    component_name = ""
    if manufacturer and device_class:
        component_name = f"{manufacturer}-{device_class}"

    return {
        "serial_number": _clean(dev, "serial_number"),
        "object_key": _clean(dev, "object_key"),
        "mac_address": _clean(dev, "mac_address"),
        "name": _clean(dev, "name"),
        "venue": _clean(meta, "venue"),
        "component_name": component_name,
        "ip_address": _clean(dev, "ip_address"),
    }


def _is_healthy(session: requests.Session, cfg: InventoryConfig) -> bool:
    try:
        resp = session.get(f"{cfg.base_url}/health", timeout=cfg.timeout_sec)
        if resp.status_code == 200:
            return True
        logger.warning(f"DeviceLookup: health check returned HTTP {resp.status_code}")
    except Exception as e:
        logger.warning(f"DeviceLookup: health check failed: {e}")
    return False


def refresh_device_lookup(
    items: list[Identifiers], cfg: InventoryConfig
) -> dict[str, dict] | None:
    """Query the Device Inventory API for every device (MAC -> serial ->
    name, first match wins) and return the new cache. Persists it to disk.
    Returns None if the API is unreachable/misconfigured, so the caller can
    keep the existing cache."""
    if not cfg.api_key or not cfg.base_url:
        logger.warning(
            "DeviceLookup: DEVICE_INVENTORY_API_KEY/BASE_URL not configured, skipping refresh"
        )
        return None

    session = requests.Session()
    if not _is_healthy(session, cfg):
        logger.warning("DeviceLookup: inventory API unreachable, keeping existing lookup")
        return None

    uniq: dict[str, Identifiers] = {}
    for it in items:
        key = it.mac or it.serial or it.name
        if key:
            uniq[key] = it

    if not uniq:
        logger.info("DeviceLookup: no devices to refresh")
        return {}

    logger.info(
        f"DeviceLookup: refreshing {len(uniq)} devices (concurrency={LOOKUP_CONCURRENCY})..."
    )
    start = time.time()

    def _lookup_one(item: tuple[str, Identifiers]):
        key, it = item
        identifier_used = ""
        raw = None
        for candidate in (it.mac, it.serial, it.name):
            if not candidate:
                continue
            identifier_used = candidate
            raw = _lookup_by_identifier(session, cfg, candidate)
            if raw is not None:
                break
        if raw is None:
            return key, None
        return key, {"identifier_used": identifier_used, "device": _extract_device_info(raw)}

    new_lookup: dict[str, dict] = {}
    found = 0
    with ThreadPoolExecutor(max_workers=LOOKUP_CONCURRENCY) as executor:
        for key, entry in executor.map(_lookup_one, uniq.items()):
            if entry is not None:
                new_lookup[key] = entry
                found += 1

    elapsed = round(time.time() - start, 1)
    logger.info(
        f"DeviceLookup: done - {found} found, {len(uniq) - found} not found, elapsed={elapsed}s"
    )

    if found == 0 and uniq:
        logger.warning("DeviceLookup: refresh found 0 devices, keeping previous cache")
        return None

    return new_lookup


def save_device_lookup(cache: dict[str, dict]) -> None:
    """Persist the (possibly merged) cache to disk. Callers that invoke
    refresh_device_lookup() incrementally (e.g. once per batch) should merge
    the result into their in-memory cache and call this afterward, rather
    than relying on refresh_device_lookup() to write the whole file itself -
    otherwise each incremental call would overwrite the file with just its
    own partial results."""
    tmp = LOOKUP_PATH + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(cache, f, indent=2)
        os.replace(tmp, LOOKUP_PATH)
    except Exception as e:
        logger.warning(f"DeviceLookup: failed to save to disk: {e}")
