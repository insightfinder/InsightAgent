"""Transform UISP metrics to InsightFinder format."""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def sanitize_instance_name(name: str) -> str:
    """Sanitize instance name to comply with InsightFinder requirements.

    InsightFinder requires instance names to not include: _ @ # :

    Args:
        name: Original instance name (device name)

    Returns:
        Sanitized instance name with underscores replaced by hyphens
        and special characters removed
    """
    # Strip leading/trailing whitespace first
    sanitized = name.strip()
    
    # Replace underscores with hyphens
    sanitized = sanitized.replace("_", "-")

    # Remove disallowed special characters: @ # :
    sanitized = re.sub(r"[@#:]", "", sanitized)

    return sanitized


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
    sanitized_instance = sanitize_instance_name(device_name)
    
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
    
    # Extract IP address (clean CIDR notation)
    device_ip = device_data.get("ipAddress", "")
    
    return {
        "in": sanitized_instance,
        "i": device_ip,
        "dit": {
            str(current_timestamp_ms): {
                "t": current_timestamp_ms,
                "metricDataPointSet": metric_data_point_set
            }
        }
    }


def transform_all_devices(
    devices_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Transform metrics for all devices into v2 API format (idm structure).

    Args:
        devices_metrics: List of device data with metrics

    Returns:
        Dictionary with instance data map (idm) containing all devices
        in v2 format, keyed by sanitized device names
    """
    idm = {}

    for device_entry in devices_metrics:
        # Transform to InsightFinder v2 format
        instance_data = transform_uisp_to_insightfinder(device_entry)

        if instance_data:
            sanitized_name = sanitize_instance_name(device_entry.get("name", "unknown"))
            idm[sanitized_name] = instance_data
            logger.info(f"Transformed {device_entry.get('type')} device: {device_entry.get('name')}")
        else:
            logger.debug(f"Skipped device (no metrics): {device_entry.get('name')}")

    return idm
