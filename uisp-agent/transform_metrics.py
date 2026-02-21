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
    # Replace underscores with hyphens
    sanitized = name.replace("_", "-")

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
    metrics_data: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Transform UISP time-series metrics to InsightFinder v2 API format.

    UISP format (per device):
    {
        "signal": [{"timestamp": 1707580800000, "avg": -44.0, "max": -42.0}, ...],
        "remoteSignal": [...],
        "signal60g": [...],
        "remoteSignal60g": [...]
    }

    InsightFinder v2 format:
    {
        "in": "device-name",
        "dit": {
            "1707580800000": {
                "t": 1707580800000,
                "metricDataPointSet": [
                    {"m": "signal_avg", "v": 44.0},
                    {"m": "signal_max", "v": 42.0},
                    ...
                ]
            },
            ...
        }
    }

    Args:
        device_data: Device information (id, name, model, etc.)
        metrics_data: Time-series metrics data from UISP

    Returns:
        Dictionary with instance data in v2 format (one instance entry)
    """
    device_name = device_data.get("name", "unknown") or "unknown"
    sanitized_instance = sanitize_instance_name(device_name)

    # Collect all unique timestamps
    timestamps: set[int] = set()
    for metric_series in metrics_data.values():
        if metric_series is not None:
            for point in metric_series:
                timestamps.add(point["timestamp"])

    # Log raw metrics data for debugging
    total_points = sum(len(v) for v in metrics_data.values() if v is not None)
    logger.debug(
        f"{device_name}: Processing {total_points} raw metric points across {len(timestamps)} unique timestamp(s)"
    )

    # Build data in timestamp map (dit)
    dit = {}

    for timestamp in sorted(timestamps):
        metric_data_point_set = []

        # Process each metric type
        metric_mappings = {
            "signal": "signal",
            "remoteSignal": "remote_signal",
            "signal60g": "signal_60ghz",
            "remoteSignal60g": "remote_signal_60ghz",
        }

        # Track which metrics have data
        null_metrics = []

        for uisp_key, metric_name in metric_mappings.items():
            if uisp_key not in metrics_data:
                continue

            # Find data point for this timestamp
            series = metrics_data[uisp_key]
            if series is None:
                continue
            point = next((p for p in series if p["timestamp"] == timestamp), None)

            if point:
                # Add avg and max as separate metrics
                if "avg" in point and point["avg"] is not None:
                    # Convert to absolute value (only positive) and to number
                    metric_data_point_set.append(
                        {"m": f"{metric_name}_avg", "v": abs(float(point["avg"]))}
                    )
                else:
                    null_metrics.append(f"{uisp_key}.avg")

                if "max" in point and point["max"] is not None:
                    # Convert to absolute value (only positive) and to number
                    metric_data_point_set.append(
                        {"m": f"{metric_name}_max", "v": abs(float(point["max"]))}
                    )
                else:
                    null_metrics.append(f"{uisp_key}.max")

        # Only add timestamp entry if it has metrics
        if metric_data_point_set:
            dit[str(timestamp)] = {
                "t": timestamp,  # Timestamp as number
                "metricDataPointSet": metric_data_point_set,
            }
        else:
            logger.debug(
                f"{device_name}: Skipped timestamp {timestamp} - all metrics are null: [{', '.join(null_metrics)}]"
            )

    # Return instance entry in v2 format
    if dit:
        return {"in": sanitized_instance, "dit": dit}

    # Log why device was filtered out
    logger.debug(
        f"{device_name}: Device filtered out - no timestamps with valid metrics (had {len(timestamps)} timestamps)"
    )
    return {}


def transform_all_devices(
    devices_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Transform metrics for all devices into v2 API format (idm structure).

    Args:
        devices_metrics: List of device data with metrics, each containing:
            - Device info (id, name, model, etc.)
            - Metrics data (signal, remoteSignal, etc.)

    Returns:
        Dictionary with instance data map (idm) containing all devices
        in v2 format, keyed by sanitized device names
    """
    idm = {}

    for device_entry in devices_metrics:
        # Separate device info from metrics
        device_info = {
            "id": device_entry.get("id"),
            "name": device_entry.get("name"),
            "model": device_entry.get("model"),
            "type": device_entry.get("type"),
            "role": device_entry.get("role"),
            "site": device_entry.get("site"),
            "status": device_entry.get("status"),
        }

        # Extract metrics data
        metrics_data = {
            key: value
            for key, value in device_entry.items()
            if key in ["signal", "remoteSignal", "signal60g", "remoteSignal60g"]
        }

        # Transform to InsightFinder v2 format
        instance_data = transform_uisp_to_insightfinder(device_info, metrics_data)

        if instance_data:
            sanitized_name = sanitize_instance_name(device_info["name"])
            idm[sanitized_name] = instance_data

    return idm
