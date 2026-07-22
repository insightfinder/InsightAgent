"""Transform UISP metrics to InsightFinder format."""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_PLACEHOLDER_VALUES = {"", "n/a", "na", "none", "null", "unknown", "tbd", "-"}


def _is_placeholder(value: str) -> bool:
    """Recognizes the inventory's various "no data" conventions the same way
    devicelookup.go's isPlaceholder does: known placeholder words, plus any
    value with no letter/digit at all."""
    trimmed = (value or "").strip()
    if trimmed.lower() in _PLACEHOLDER_VALUES:
        return True
    return not any(c.isalnum() for c in trimmed)


def inv_field(d: dict, key: str) -> str:
    """Read a string field from an Inventory dict, treating placeholders as missing."""
    v = (d or {}).get(key)
    if not isinstance(v, str) or _is_placeholder(v):
        return ""
    return v


def normalize_mac(mac: str) -> str:
    """':' -> '-', trim leading/trailing '-'. No case conversion."""
    mac = (mac or "").strip()
    if not mac:
        return ""
    converted = mac.replace(":", "-").strip("-")
    return converted if any(c.isalnum() for c in converted) else ""


def clean_own_name(name: str) -> str:
    """'_' and ':' both -> '-' (matches devicelookup.go's CleanOwnName)."""
    name = (name or "").strip()
    if not name:
        return ""
    return name.replace("_", "-").replace(":", "-").strip("-")


def build_instance_name(inv_record: dict, own_name: str) -> str | None:
    """Instance name preference: Inventory MAC > Inventory serial > Inventory
    object_key > the device's own name (cleaned). Returns None if none of
    these are available - the caller must drop the device rather than send
    it under any other fallback identifier. No uppercase/lowercase conversion
    anywhere."""
    inv_mac = normalize_mac(inv_field(inv_record, "mac_address"))
    if inv_mac:
        return f"MAC {inv_mac}"
    inv_serial = inv_field(inv_record, "serial_number")
    if inv_serial:
        return f"SERIAL {inv_serial}"
    inv_object_key = inv_field(inv_record, "object_key")
    if inv_object_key:
        return f"JIRAKEY {inv_object_key}"
    cleaned_own = clean_own_name(own_name)
    if cleaned_own:
        return cleaned_own
    return None


def component_name_from_lookup(inv_record: dict) -> str:
    """Return 'Manufacturer-DeviceClass' from the matched Inventory record, or
    empty string. Only set when both are present in Inventory - no default."""
    model = (inv_record or {}).get("model") or {}
    manufacturer = inv_field(model, "manufacturer")
    device_class = inv_field(model, "device_class")
    if manufacturer and device_class:
        return f"{manufacturer}-{device_class}"
    return ""


def sanitize_metric_name(name: str) -> str:
    """Sanitize metric name to comply with InsightFinder requirements.

    InsightFinder requires metric names to not include: [] space :

    Args:
        name: Original metric name

    Returns:
        Sanitized metric name
    """
    # Remove brackets and colons
    sanitized = re.sub(r"[\[\]:]", "", name)

    # Replace spaces with underscores
    sanitized = sanitized.replace(" ", "_")

    return sanitized


def transform_uisp_to_insightfinder(
    device_data: dict[str, Any],
    device_lookup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Transform UISP device metrics to InsightFinder v2 API format.

    Extracts device overview metrics and converts them to InsightFinder format.
    
    UISP device overview structure:
    {
        "id": "device-id",
        "name": "device-name",
        "type": "airFiber|airMax|olt|onu",
        "signal": -20 (dBm, optional),
        "downlinkUtilization": 0.024,
        "uplinkUtilization": 0.001,
        "linkActiveStationsCount": 7,
        "receivePower": -19.546 (ONU only),
        "stationsCount": 28 (OLT only)
    }

    InsightFinder v2 format (single timestamp):
    {
        "in": "device-name",
        "dit": {
            "{current_timestamp}": {
                "t": {current_timestamp},
                "metricDataPointSet": [
                    {"m": "signal", "v": 20.0},
                    {"m": "downlink_utilization", "v": 2.4},
                    ...
                ]
            }
        }
    }

    Args:
        device_data: Device data with metrics from UISP

    Returns:
        Dictionary with instance data in v2 format (one instance entry)
    """
    device_name = device_data.get("name", "unknown") or "unknown"
    device_type = device_data.get("type", "unknown")
    mac_raw = (device_data.get("mac") or "").lower()

    lookup = device_lookup or {}
    inv_record = (lookup.get(mac_raw) or {}).get("devices") or {}

    # Instance name: Inventory MAC > Inventory serial > Inventory object_key >
    # the device's own name. If none of these are available (Inventory miss
    # and no own name), drop the device - never sent under any other fallback
    # identifier. An Inventory miss alone does NOT drop the device.
    instance = build_instance_name(inv_record, device_name)
    if instance is None:
        logger.debug(f"{device_name}: dropped - no Inventory match and no usable own name")
        return {}

    # Use current timestamp in milliseconds
    import time
    current_timestamp_ms = int(time.time() * 1000)
    
    metric_data_point_set = []
    
    # Extract metrics based on device type
    if device_type in ["airFiber", "airMax"]:
        # Wireless devices (PTP/PTMP/WiFi AP)
        
        # Signal (convert to absolute value if present)
        if device_data.get("signal") is not None:
            metric_data_point_set.append({
                "m": "signal",
                "v": abs(float(device_data["signal"]))
            })
        
        # Downlink Utilization (convert decimal to percentage)
        if device_data.get("downlinkUtilization") is not None:
            dl_util = float(device_data["downlinkUtilization"]) * 100
            metric_data_point_set.append({
                "m": "downlinkUtilization",
                "v": dl_util
            })
        
        # Uplink Utilization (convert decimal to percentage)
        if device_data.get("uplinkUtilization") is not None:
            ul_util = float(device_data["uplinkUtilization"]) * 100
            metric_data_point_set.append({
                "m": "uplinkUtilization",
                "v": ul_util
            })
        
        # Total Capacity
        if device_data.get("capacity") is not None:
            capacity = float(device_data["capacity"])
            metric_data_point_set.append({
                "m": "capacity",
                "v": capacity
            })
        
        # Active Stations Count
        if device_data.get("linkActiveStationsCount") is not None:
            metric_data_point_set.append({
                "m": "Total Clients",
                "v": float(device_data["linkActiveStationsCount"])
            })
        
        # First station metrics (if available)
        stations = device_data.get("stations")
        if stations:
            # Only use the first station
            station = stations[0]
            
            if station.get("downlinkCapacity") is not None:
                metric_data_point_set.append({
                    "m": "downlinkCapacity",
                    "v": float(station["downlinkCapacity"])
                })
            
            if station.get("uplinkCapacity") is not None:
                metric_data_point_set.append({
                    "m": "uplinkCapacity",
                    "v": float(station["uplinkCapacity"])
                })
            
            if station.get("txMcs") is not None:
                metric_data_point_set.append({
                    "m": "txMcs",
                    "v": float(station["txMcs"])
                })
            
            if station.get("rxMcs") is not None:
                metric_data_point_set.append({
                    "m": "rxMcs",
                    "v": float(station["rxMcs"])
                })
    
    elif device_type == "olt":
        # Fiber OLT (access point)
        if device_data.get("stationsCount") is not None:
            metric_data_point_set.append({
                "m": "activeStationsCount",
                "v": float(device_data["stationsCount"])
            })
    
    elif device_type == "onu":
        # Fiber ONU (client)
        
        # Signal (optical power, convert to absolute value)
        if device_data.get("signal") is not None:
            metric_data_point_set.append({
                "m": "signal",
                "v": abs(float(device_data["signal"]))
            })
        
        # Receive Power
        if device_data.get("receivePower") is not None:
            metric_data_point_set.append({
                "m": "receivePower",
                "v": abs(float(device_data["receivePower"]))
            })
        
        # RX Rate (receive bit rate in bits/sec)
        if device_data.get("rxRate") is not None:
            metric_data_point_set.append({
                "m": "rxRate",
                "v": float(device_data["rxRate"])
            })
        
        # TX Rate (transmit bit rate in bits/sec)
        if device_data.get("txRate") is not None:
            metric_data_point_set.append({
                "m": "txRate",
                "v": float(device_data["txRate"])
            })
    
    # Only return if we have metrics
    if not metric_data_point_set:
        logger.debug(f"{device_name}: No metrics extracted for device type {device_type}")
        return {}

    # Instance metadata (display name / component name / IP / zone) must be
    # packed into a single "im" JSON string, not sent as flat top-level keys -
    # matches baicells-agent/tarana-gnmic-agent's validated wire format.
    own_ip = device_data.get("ipAddress", "") or ""
    im_data: dict[str, str] = {}
    # Display name: always the device's own raw name as reported, uncleaned -
    # never falls back to the Inventory's name field.
    if device_name:
        im_data["idn"] = device_name
    cn = component_name_from_lookup(inv_record)
    if cn:
        im_data["cn"] = cn
    # IP: Inventory ip_address > the device's own reported IP.
    ip = inv_field(inv_record, "ip_address") or own_ip
    if ip:
        im_data["i"] = ip
    # Zone: Inventory's subvenue only - omitted if not in Inventory.
    zone = inv_field(inv_record.get("meta") or {}, "subvenue")
    if zone:
        im_data["z"] = zone

    result = {
        "in": instance,
        "dit": {
            str(current_timestamp_ms): {
                "t": current_timestamp_ms,
                "metricDataPointSet": metric_data_point_set
            }
        }
    }
    if im_data:
        result["im"] = json.dumps(im_data)
    return result


def transform_all_devices(
    devices_metrics: list[dict[str, Any]],
    device_lookup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Transform metrics for all devices into v2 API format (idm structure).

    Args:
        devices_metrics: List of device data with metrics
        device_lookup: Matched Device Inventory cache (devicelookup.json),
            keyed by lowercased MAC - see build_instance_name for how it's used

    Returns:
        Dictionary with instance data map (idm) containing all devices
        in v2 format, keyed by the resolved instance name (see
        build_instance_name) - not the raw device name
    """
    idm = {}

    for device_entry in devices_metrics:
        # Transform to InsightFinder v2 format
        instance_data = transform_uisp_to_insightfinder(device_entry, device_lookup)

        if instance_data:
            idm[instance_data["in"]] = instance_data
            logger.info(f"Transformed {device_entry.get('type')} device: {device_entry.get('name')}")
        else:
            logger.debug(f"Skipped device (no metrics or no usable identity): {device_entry.get('name')}")

    return idm
