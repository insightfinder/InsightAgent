"""
Jira Assets → SQLite sync.

Attribute IDs sourced directly from the AccessParks workspace schema
(objecttype/45/attributes endpoint — verified 2026-05-19).
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .database import SessionLocal
from .repository import DeviceRepository

logger = logging.getLogger(__name__)

# ── Attribute ID → field name ─────────────────────────────────────────────────
# type=1 attributes are object references; displayValue gives the label.
# Attributes handled as dedicated DB columns are noted with *.
ATTR_MAP: Dict[int, str] = {
    382: "object_key",                          # * Key (IHS-xxxxx)
    450: "status",
    383: "device_name",                         # * DeviceName (short, e.g. "APi")
    387: "full_name",                           # FullName / label
    388: "subvenue",                            # Subvenue (ref → displayValue)
    389: "location",                            # Location (ref → displayValue)
    390: "ip_address",                          # * management_ip
    639: "ipv6_address",                        # ipv6_address/length
    638: "dhcpv6_prefix",                       # dhcpv6_prefix/length
    391: "mac_address",                         # * management_mac
    392: "serial_number",                       # * serial_number
    393: "manufacturer",                        # manufacturer (ref → displayValue)
    394: "model",                               # model (ref → model_id)
    399: "powered_by",
    471: "upstream_junction_port",
    421: "uplink_port",
    401: "upstream_device_port",
    396: "height",
    398: "tilt",
    397: "azimuth",
    488: "behind_l3nat",
    480: "frequency",
    481: "channel_width",
    569: "phy_rate",
    570: "phy_rate_alarm_threshold",
    479: "eirp",
    476: "target_signal_level",
    477: "installed_signal_level",
    571: "installed_signal_level_alarm_threshold",
    402: "notes",
    470: "nonpropagated_notes",
    395: "zabbix_host_id",                      # * zabbix_host_id
    403: "update_trigger",
    384: "created_date",
    385: "updated_date",
    549: "show_in_maps",
    550: "latitude",
    551: "longitude",
    598: "purchase_date",
    599: "install_date",
    675: "subvenue_root_device_for_monitoring",
    744: "upstream_path_bends",
}

# Attributes that become dedicated DB columns (not only stored in meta)
COLUMN_FIELDS = {"object_key", "device_name", "ip_address", "mac_address",
                 "serial_number", "zabbix_host_id"}

# Edge attribute IDs
UPSTREAM_DEVICE_ATTR = 400
UPSTREAM_JUNCTION_ATTR = 461

# Subvenue attribute that holds the parent Venue reference (objecttype Subvenue, attr 225)
SUBVENUE_VENUE_ATTR_ID = 225

# ── Model attribute map (objecttype 13, verified 2026-05-19) ─────────────────
MODEL_ATTR_MAP: Dict[int, str] = {
    92:  "object_key",
    93:  "name",                          # model name (plain text)
    563: "description",
    96:  "manufacturer",                  # ref → displayValue
    329: "device_class",                  # * "Wifi.Indoor", "Backhaul", etc.
    460: "backhaul_technology_stacks",
    332: "input_voltage",
    333: "input_amperage",
    334: "poe_standard",
    331: "beamwidth",
    330: "required_attributes",
    556: "required_accessories",
    475: "optional_accessories",
    557: "accessory_calculation_notes",
    336: "install_mops",
    335: "notes",
    451: "access_method",
    373: "zabbix_icon_id",
    482: "zabbix_icon_disabled_id",
    457: "zabbix_model_monitoring_mode",  # * dedicated column
    281: "zabbix_model_snmp_template_id", # * dedicated column
    94:  "created_date",
    95:  "updated_date",
    483: "install_hours",
    484: "config_hours",
    486: "group_config_hours",
    487: "revisit_factor",
    485: "testing_hours",
    588: "classtype",                     # * lowercase variant of class
}

# Dedicated DB columns on DeviceModel (not only stored in meta)
MODEL_COLUMN_FIELDS = {
    "device_class", "classtype",
    "zabbix_model_monitoring_mode", "zabbix_model_snmp_template_id",
    "manufacturer",
}

BATCH_SIZE = 500
PAGE_SIZE = 25
MAX_RETRIES = 3


class JiraClient:
    def __init__(self):
        self.email = os.environ["JIRA_EMAIL"]
        self.token = os.environ["JIRA_API_TOKEN"]
        self.workspace_id = os.environ["JIRA_WORKSPACE_ID"]
        self._base = (
            f"https://api.atlassian.com/jsm/assets/workspace/{self.workspace_id}/v1"
        )

    @property
    def _auth(self) -> Tuple[str, str]:
        return (self.email, self.token)

    async def _fetch_page(self, aql: str, page: int) -> List[Dict]:
        backoff = 2
        for attempt in range(MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    r = await client.get(
                        f"{self._base}/aql/objects",
                        auth=self._auth,
                        params={"qlQuery": aql, "page": page, "resultsPerPage": PAGE_SIZE},
                    )
                    r.raise_for_status()
                    data = r.json()
                    return data.get("objectEntries") or data.get("values") or []
            except (httpx.ReadError, httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt < MAX_RETRIES:
                    wait = backoff * (2 ** attempt)
                    logger.warning("Page %d attempt %d failed (%s), retry in %ds",
                                   page, attempt + 1, exc, wait)
                    await asyncio.sleep(wait)
                else:
                    raise

    async def fetch_all(self, object_type: str) -> List[Dict]:
        aql = f'objectType = "{object_type}"'
        all_objects: List[Dict] = []
        seen: set = set()
        page = 1
        while True:
            objects = await self._fetch_page(aql, page)
            if not objects:
                break
            for obj in objects:
                key = obj.get("objectKey") or obj.get("id")
                if key not in seen:
                    all_objects.append(obj)
                    seen.add(key)
            logger.info("Fetched %s page %d: %d objects (total %d)",
                        object_type, page, len(objects), len(all_objects))
            if len(objects) < PAGE_SIZE:
                break
            page += 1
        return all_objects

    async def fetch_one(self, object_id: str) -> Optional[Dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{self._base}/object/{object_id}",
                auth=self._auth,
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()


def _attr_display(obj: Dict, attr_id: int) -> Optional[str]:
    for attr in obj.get("attributes", []):
        if str(attr.get("objectTypeAttributeId")) == str(attr_id):
            vals = attr.get("objectAttributeValues", [])
            if vals:
                return vals[0].get("displayValue") or vals[0].get("value")
    return None


def transform_models(raw: List[Dict]) -> List[Dict]:
    out = []
    for obj in raw:
        obj_id = str(obj["id"])
        record: Dict[str, Any] = {
            "id": obj_id,
            "name": obj.get("label") or obj.get("objectKey", ""),
            "manufacturer": None,
            "device_class": None,
            "classtype": None,
            "zabbix_model_monitoring_mode": None,
            "zabbix_model_snmp_template_id": None,
            "meta": {"object_key": obj.get("objectKey", "")},
        }

        for attr in obj.get("attributes", []):
            try:
                attr_id = int(attr.get("objectTypeAttributeId"))
            except (TypeError, ValueError):
                continue

            vals = attr.get("objectAttributeValues", [])
            if not vals:
                continue
            val_str = vals[0].get("displayValue") or vals[0].get("value")
            if not val_str:
                continue

            field = MODEL_ATTR_MAP.get(attr_id)
            if not field:
                continue

            if field == "name":
                if val_str:
                    record["name"] = val_str
            elif field in MODEL_COLUMN_FIELDS:
                record[field] = val_str
                record["meta"][field] = val_str
            else:
                record["meta"][field] = val_str

        out.append(record)
    return out


def transform_subvenues(raw: List[Dict]) -> Dict[str, Dict[str, Optional[str]]]:
    """Returns {subvenue_id: {name, venue_id, venue_name}} by reading attr 225 from each Subvenue."""
    result: Dict[str, Dict[str, Optional[str]]] = {}
    for obj in raw:
        obj_id = str(obj["id"])
        subvenue_name = obj.get("label") or ""
        venue_id: Optional[str] = None
        venue_name: Optional[str] = None
        for attr in obj.get("attributes", []):
            if str(attr.get("objectTypeAttributeId")) == str(SUBVENUE_VENUE_ATTR_ID):
                vals = attr.get("objectAttributeValues", [])
                if vals:
                    venue_name = vals[0].get("displayValue") or vals[0].get("value")
                    ref_obj = vals[0].get("referencedObject") or {}
                    raw_vid = ref_obj.get("id")
                    venue_id = str(raw_vid) if raw_vid else None
                break
        result[obj_id] = {
            "name": subvenue_name,
            "venue_id": venue_id,
            "venue_name": venue_name,
        }
    return result


def _transform_one_device(obj: Dict, subvenue_map: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> Tuple[Dict, List[Dict]]:
    """Transform a single raw Jira object into (device_record, edge_records)."""
    obj_id = str(obj["id"])
    object_key = obj.get("objectKey", "")
    label = obj.get("label", "")
    # label is FullName in Jira — use it as the primary name
    default_name = object_key if (not label or label == "--") else label

    device: Dict[str, Any] = {
        "id": obj_id,
        "name": default_name,
        "device_name": None,
        "ip_address": None,
        "mac_address": None,
        "serial_number": None,
        "object_key": object_key,
        "zabbix_host_id": None,
        "model_id": None,
        "meta": {"object_key": object_key, "device_id": obj_id},
    }
    edges: List[Dict] = []

    for attr in obj.get("attributes", []):
        try:
            attr_id = int(attr.get("objectTypeAttributeId"))
        except (TypeError, ValueError):
            continue

        vals = attr.get("objectAttributeValues", [])
        if not vals:
            continue

        val_str = vals[0].get("displayValue") or vals[0].get("value")

        # ── edges ─────────────────────────────────────────────────────────────
        if attr_id == UPSTREAM_DEVICE_ATTR:
            for v in vals:
                ref_id = (v.get("referencedObject") or {}).get("id")
                if ref_id:
                    edges.append({
                        "id": f"{ref_id}-{obj_id}-upstream_device",
                        "source_id": str(ref_id),
                        "target_id": obj_id,
                        "relationship_type": "upstream_device",
                    })
            continue

        if attr_id == UPSTREAM_JUNCTION_ATTR:
            for v in vals:
                ref_id = (v.get("referencedObject") or {}).get("id")
                if ref_id:
                    edges.append({
                        "id": f"{ref_id}-{obj_id}-upstream_junction",
                        "source_id": str(ref_id),
                        "target_id": obj_id,
                        "relationship_type": "upstream_junction",
                    })
            continue

        # ── mapped attributes ─────────────────────────────────────────────────
        field = ATTR_MAP.get(attr_id)
        if not field:
            continue

        if field == "model":
            ref_id = (vals[0].get("referencedObject") or {}).get("id")
            if ref_id:
                device["model_id"] = str(ref_id)
            if val_str:
                device["meta"]["model"] = val_str

        elif field == "device_name":
            device["device_name"] = val_str
            device["meta"]["device_name"] = val_str

        elif field == "full_name":
            # FullName overrides label-derived name when set
            if val_str and val_str != "--":
                device["name"] = val_str
            device["meta"]["full_name"] = val_str

        elif field == "subvenue":
            ref_id = str((vals[0].get("referencedObject") or {}).get("id") or "")
            if val_str:
                device["meta"]["subvenue"] = val_str
            if ref_id:
                device["meta"]["subvenue_id"] = ref_id
            if ref_id and subvenue_map:
                sv = subvenue_map.get(ref_id)
                if sv:
                    device["meta"]["venue"] = sv.get("venue_name")
                    if sv.get("venue_id"):
                        device["meta"]["venue_id"] = sv["venue_id"]

        elif field == "location":
            ref_id = str((vals[0].get("referencedObject") or {}).get("id") or "")
            if val_str:
                device["meta"]["location"] = val_str
            if ref_id:
                device["meta"]["location_id"] = ref_id

        elif field in COLUMN_FIELDS:
            device[field] = val_str
            device["meta"][field] = val_str

        else:
            if val_str:
                device["meta"][field] = val_str

    return device, edges


def transform_devices(
    raw: List[Dict],
    subvenue_map: Optional[Dict[str, Dict[str, Optional[str]]]] = None,
) -> Tuple[List[Dict], List[Dict]]:
    devices: List[Dict] = []
    edges: List[Dict] = []
    for obj in raw:
        d, e = _transform_one_device(obj, subvenue_map=subvenue_map)
        devices.append(d)
        edges.extend(e)
    return devices, edges


async def run_sync() -> Dict[str, Any]:
    """Full sync: Jira → SQLite. Returns counts and timing."""
    client = JiraClient()
    t0 = time.time()

    # Fetch models, devices, and subvenues in parallel
    logger.info("Fetching Model, Device, and Subvenue objects from Jira in parallel...")
    raw_models, raw_devices, raw_subvenues = await asyncio.gather(
        client.fetch_all("Model"),
        client.fetch_all("Device"),
        client.fetch_all("Subvenue"),
    )

    fetch_time = time.time() - t0
    logger.info("Fetched %d models, %d devices, %d subvenues in %.1fs",
                len(raw_models), len(raw_devices), len(raw_subvenues), fetch_time)

    subvenue_map = transform_subvenues(raw_subvenues)
    model_records = transform_models(raw_models)
    device_records, edge_records = transform_devices(raw_devices, subvenue_map=subvenue_map)

    t1 = time.time()
    async with SessionLocal() as session:
        repo = DeviceRepository(session)

        for i in range(0, len(model_records) or 1, BATCH_SIZE):
            batch = model_records[i: i + BATCH_SIZE]
            if batch:
                await repo.upsert_models(batch)
                await session.commit()

        for i in range(0, len(device_records) or 1, BATCH_SIZE):
            batch = device_records[i: i + BATCH_SIZE]
            if batch:
                await repo.upsert_devices(batch)
                await session.commit()

        for i in range(0, len(edge_records) or 1, BATCH_SIZE):
            batch = edge_records[i: i + BATCH_SIZE]
            if batch:
                await repo.upsert_edges(batch)
                await session.commit()

    write_time = time.time() - t1
    return {
        "models": len(model_records),
        "devices": len(device_records),
        "edges": len(edge_records),
        "fetch_seconds": round(fetch_time, 1),
        "write_seconds": round(write_time, 1),
        "total_seconds": round(time.time() - t0, 1),
    }
