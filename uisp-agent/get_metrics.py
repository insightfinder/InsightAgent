#!/usr/bin/env python3
"""
UISP Device Signal Metrics Fetcher
Fetches signal strength metrics (signal, remoteSignal, signal60g, remoteSignal60g) from UISP devices.
Only processes active devices with 60GHz radio capability and valid signal data.

Usage:
    python get_metrics.py              # Get all active 60GHz devices with signal metrics (default: last hour)
    python get_metrics.py -n 5         # Limit to first 5 devices
    python get_metrics.py --period 10m   # Get metrics for last 10 minutes
    python get_metrics.py --period 30m   # Get metrics for last 30 minutes
    python get_metrics.py --period 2h    # Get metrics for last 2 hours
    python get_metrics.py --period 7d    # Get metrics for last 7 days
    python get_metrics.py --num-points 10  # Limit to 10 data points (default: all points)
    python get_metrics.py --sample-interval 5m  # Sample every 5 minutes
    python get_metrics.py --start 1707580800000  # Specify start time in epoch ms
"""

import argparse
import logging
import os
import re
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
import urllib3

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables from .env file in the script's directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

UISP_URL = os.getenv("UISP_URL", "").rstrip("/")
API_TOKEN = os.getenv("API_TOKEN") or os.getenv("UISP_API_TOKEN")

BASE_API = f"{UISP_URL}/nms/api/v2.1"


def is_active_60ghz_device(device):
    """Check if device is active with signal and 60GHz radio."""
    overview = device.get("overview", {})
    features = device.get("features", {})
    return (
        overview.get("status", "").lower() == "active"
        and overview.get("signal") is not None
        and features.get("has60GhzRadio", False)
    )


def matches_device_filter(device, search_term):
    """Check if device matches the search filter."""
    identification = device.get("identification", {})
    device_name = (identification.get("name") or "").lower()
    device_id = (identification.get("id") or "").lower()
    return search_term in device_name or search_term in device_id


def get_devices(token):
    """Get list of all devices."""
    url = f"{BASE_API}/devices"
    headers = {"x-auth-token": token}

    print("\nFetching devices...")
    response = requests.get(url, headers=headers, verify=False)

    if response.status_code == 200:
        devices = response.json()
        active_count = sum(1 for d in devices if is_active_60ghz_device(d))
        print(
            f"✓ Found {active_count} active 60GHz devices with signal (of {len(devices)} total)"
        )
        return devices
    else:
        print(f"✗ Failed to fetch devices: {response.status_code}")
        print(f"Response: {response.text}")
        return []


def get_device_statistics(token, device_id, period="1h", start_ms=None):
    """
    Get signal statistics for a device.

    Args:
        token: Auth token
        device_id: Device UUID
        period: Time period to fetch (e.g., '10m', '1h', '2d')
        start_ms: Optional start time in epoch milliseconds. If not provided, calculated from current time.

    Returns:
        Statistics dict with signal fields (signal, signal60g, remoteSignal60g)
    """
    url = f"{BASE_API}/devices/{device_id}/statistics"
    headers = {"x-auth-token": token}

    # Parse period string to extract number and unit
    match = re.match(r"^(\d+)([mhd])$", period)
    if not match:
        raise ValueError(
            f"Invalid period format: {period}. Use format like '30m', '2h', or '1d'"
        )

    amount = int(match.group(1))
    unit = match.group(2)

    # Convert to milliseconds
    unit_ms = {
        "m": 60 * 1000,
        "h": 60 * 60 * 1000,
        "d": 24 * 60 * 60 * 1000,
    }

    period_ms = amount * unit_ms[unit]

    # Use provided start time or calculate from current time
    if start_ms is None:
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - period_ms  # Start time is period ago from now

    params = {
        "interval": "range",  # Always use 'range'
        "start": str(start_ms),  # Start time in epoch ms
        "period": str(period_ms),  # Period in ms from start
    }

    try:
        response = requests.get(
            url, headers=headers, params=params, verify=False, timeout=30
        )

        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        return None


def detect_gaps(points, sample_interval_ms, metric_name=""):
    """Detect gaps in time series data.

    Args:
        points: List of data points with timestamps
        sample_interval_ms: Expected interval between points in milliseconds
        metric_name: Name of metric for logging

    Returns:
        List of detected gaps as tuples (gap_start_time, gap_end_time, missing_count)
    """
    if not points or len(points) < 2:
        return []

    gaps = []
    tolerance_ms = sample_interval_ms * 0.2  # 20% tolerance

    for i in range(len(points) - 1):
        current_ts = points[i]["timestamp"]
        next_ts = points[i + 1]["timestamp"]
        gap_ms = next_ts - current_ts

        # Check if gap is larger than expected interval (with tolerance)
        if gap_ms > (sample_interval_ms + tolerance_ms):
            missing_intervals = int(gap_ms / sample_interval_ms) - 1
            if missing_intervals > 0:
                gaps.append((current_ts, next_ts, missing_intervals))

                # Format timestamps for logging
                gap_start = datetime.fromtimestamp(current_ts / 1000).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                gap_end = datetime.fromtimestamp(next_ts / 1000).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                gap_duration_min = gap_ms / (60 * 1000)

                logger.debug(
                    f"Gap detected in {metric_name}: {gap_start} to {gap_end} "
                    f"({gap_duration_min:.1f} min, ~{missing_intervals} missing points)"
                )

    return gaps


def get_time_series(
    stat_obj, num_points=None, sample_interval="1m", metric_name="metric"
):
    """Extract last N time-series points with avg and max aligned by timestamp.

    This function rounds second-level timestamps to minute boundaries and picks
    the latest data point within each minute. When multiple data points exist
    within the same minute, the most recent one is selected (not averaged).
    This reduces gaps caused by second-level variations when InsightFinder
    expects minute-level data.

    Args:
        stat_obj: Statistics object from UISP API
        num_points: Number of most recent points to return (None = all)
        sample_interval: Minimum interval between points (e.g., '1m', '5m')
        metric_name: Name of the metric for logging purposes

    Returns:
        List of data points with timestamps rounded to minutes, latest values selected
    """
    if stat_obj is None:
        return None

    if not isinstance(stat_obj, dict):
        return None

    avg_data = stat_obj.get("avg", [])
    max_data = stat_obj.get("max", [])

    if not isinstance(avg_data, list) or not isinstance(max_data, list):
        return None

    # Parse sample interval first to determine if we need to round timestamps
    match = re.match(r"^(\d+)([mh])$", sample_interval)
    if not match:
        raise ValueError(
            f"Invalid sample interval format: {sample_interval}. Use format like '1m', '5m', '1h'"
        )

    amount = int(match.group(1))
    unit = match.group(2)

    unit_ms = {
        "m": 60 * 1000,
        "h": 60 * 60 * 1000,
    }

    sample_interval_ms = amount * unit_ms[unit]

    # Round timestamps to minute boundaries for minute-level granularity
    # This allows us to aggregate second-level data into minute-level buckets
    def round_to_minute(timestamp_ms):
        """Round timestamp to the nearest minute (floor)."""
        minute_ms = 60 * 1000
        return (timestamp_ms // minute_ms) * minute_ms

    # Build a dict mapping rounded timestamp to list of (original_timestamp, value) tuples
    # This allows us to pick the latest value when multiple points exist in the same minute
    time_buckets = {}

    for point in avg_data:
        if isinstance(point, dict) and point.get("x") is not None:
            timestamp = point.get("x")
            rounded_ts = round_to_minute(timestamp)

            if rounded_ts not in time_buckets:
                time_buckets[rounded_ts] = {"avg_points": [], "max_points": []}

            if point.get("y") is not None:
                time_buckets[rounded_ts]["avg_points"].append(
                    (timestamp, point.get("y"))
                )

    for point in max_data:
        if isinstance(point, dict) and point.get("x") is not None:
            timestamp = point.get("x")
            rounded_ts = round_to_minute(timestamp)

            if rounded_ts not in time_buckets:
                time_buckets[rounded_ts] = {"avg_points": [], "max_points": []}

            if point.get("y") is not None:
                time_buckets[rounded_ts]["max_points"].append(
                    (timestamp, point.get("y"))
                )

    # For each minute bucket, pick the latest (most recent) value
    time_series = {}
    aggregation_count = 0
    for rounded_ts, bucket in time_buckets.items():
        avg_val = None
        max_val = None

        # Count if we're aggregating multiple points
        total_points = len(bucket["avg_points"]) + len(bucket["max_points"])
        if total_points > 2:  # More than one data point (avg+max pair)
            aggregation_count += 1

        # Pick the latest avg value (highest original timestamp)
        if bucket["avg_points"]:
            latest_avg_point = max(bucket["avg_points"], key=lambda x: x[0])
            avg_val = latest_avg_point[1]

        # Pick the latest max value (highest original timestamp)
        if bucket["max_points"]:
            latest_max_point = max(bucket["max_points"], key=lambda x: x[0])
            max_val = latest_max_point[1]

        # Only create time_series entry if at least one value is not None
        # This prevents creating data points with all null values that would be filtered out later
        if avg_val is not None or max_val is not None:
            time_series[rounded_ts] = {
                "timestamp": rounded_ts,
                "avg": avg_val,
                "max": max_val,
            }

    # Log if aggregation occurred
    original_point_count = len(avg_data) + len(max_data)
    if aggregation_count > 0:
        logger.debug(
            f"{metric_name}: Aggregated {original_point_count} second-level points into {len(time_series)} minute-level buckets"
        )

    # Sort by timestamp
    sorted_points = sorted(time_series.values(), key=lambda p: p["timestamp"])
    raw_point_count = len(sorted_points)

    # Filter to keep only points at least sample_interval apart
    if not sorted_points:
        return None

    filtered_points = []
    last_timestamp = None

    for point in sorted_points:
        if (
            last_timestamp is None
            or (point["timestamp"] - last_timestamp) >= sample_interval_ms
        ):
            filtered_points.append(point)
            last_timestamp = point["timestamp"]

    # Log data point counts
    filtered_count = len(filtered_points)
    if raw_point_count != filtered_count:
        logger.debug(
            f"{metric_name}: {raw_point_count} raw points → {filtered_count} after {sample_interval} filtering"
        )

    # Detect gaps in the filtered data
    if filtered_points:
        gaps = detect_gaps(filtered_points, sample_interval_ms, metric_name)
        if gaps:
            total_missing = sum(gap[2] for gap in gaps)
            logger.debug(
                f"{metric_name}: Detected {len(gaps)} gap(s) with ~{total_missing} missing data points"
            )

    # Return last N points from filtered data (or all if num_points is None)
    if not filtered_points:
        return None

    final_points = filtered_points[-num_points:] if num_points else filtered_points

    if num_points and len(final_points) < num_points:
        logger.debug(
            f"{metric_name}: Requested {num_points} points, but only {len(final_points)} available"
        )

    return final_points


def extract_statistics(
    stats_data, num_points=None, sample_interval="1m", device_name="device"
):
    """Extract key statistics from the statistics API response.

    Args:
        stats_data: Raw statistics data from UISP API
        num_points: Number of most recent points to return (None = all)
        sample_interval: Minimum interval between points (e.g., '1m', '5m')
        device_name: Device name for logging purposes

    Returns:
        Dictionary containing signal metrics time series
    """
    if not stats_data:
        return {}

    result = {}

    # Signal metrics (extract last N time-series points)
    result["signal"] = get_time_series(
        stats_data.get("signal"), num_points, sample_interval, f"{device_name}/signal"
    )
    result["remoteSignal"] = get_time_series(
        stats_data.get("remoteSignal"),
        num_points,
        sample_interval,
        f"{device_name}/remoteSignal",
    )
    result["signal60g"] = get_time_series(
        stats_data.get("signal60g"),
        num_points,
        sample_interval,
        f"{device_name}/signal60g",
    )
    result["remoteSignal60g"] = get_time_series(
        stats_data.get("remoteSignal60g"),
        num_points,
        sample_interval,
        f"{device_name}/remoteSignal60g",
    )

    # Log total data point counts
    total_points = sum(len(v) for v in result.values() if v is not None)
    if total_points > 0:
        logger.debug(
            f"{device_name}: Extracted {total_points} total data points across all metrics"
        )

    return result


def extract_device_info(device):
    """Extract basic device info."""
    info = {}

    # Basic device info
    identification = device.get("identification", {})
    info["id"] = identification.get("id", "")
    info["name"] = identification.get("name", "Unknown")
    info["model"] = identification.get("model", "")
    info["type"] = identification.get("type", "")
    info["role"] = identification.get("role", "")
    site_info = identification.get("site")
    info["site"] = site_info.get("name", "") if site_info else ""

    # Status and signal
    overview = device.get("overview", {})
    info["status"] = overview.get("status", "")
    info["signal"] = overview.get("signal")

    return info


def print_device_info(info, indent="  ", show_signal=True):
    """Print basic device information."""
    print(f"{indent}ID: {info.get('id') or 'N/A'}")
    print(f"{indent}Model: {info.get('model') or 'N/A'}")
    print(
        f"{indent}Type: {info.get('type') or 'N/A'} | Role: {info.get('role') or 'N/A'}"
    )
    print(f"{indent}Site: {info.get('site') or 'N/A'}")
    print(f"{indent}Status: {info.get('status') or 'N/A'}")

    if show_signal:
        signal_val = info.get("signal")
        print(
            f"{indent}Signal: {signal_val} dBm"
            if signal_val is not None
            else f"{indent}Signal: N/A"
        )


def print_signal_metrics(info, stats=None, num_points=None):
    """Print signal metrics for a device."""
    print(f"\n{'=' * 60}")
    print(f"Device: {info['name']}")
    print(f"{'=' * 60}")
    print_device_info(info)

    # Signal metrics from statistics
    if not stats:
        return

    def print_metric_series(metric_name, data, num_points):
        """Helper to print time series data for a metric."""
        if not data:
            return False
        count = len(data)
        points_label = f"All {count}" if num_points is None else f"Latest {num_points}"
        print(f"\n  {metric_name} ({points_label} values):")
        print(f"    {'Timestamp':<20} {'Avg (dBm)':<12} {'Max (dBm)':<12}")
        print(f"    {'-' * 44}")
        for point in data:
            ts = datetime.fromtimestamp(point["timestamp"] / 1000).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            avg_val = f"{point['avg']:.1f}" if point["avg"] is not None else "N/A"
            max_val = f"{point['max']:.1f}" if point["max"] is not None else "N/A"
            print(f"    {ts:<20} {avg_val:<12} {max_val:<12}")
        return True

    has_data = any(
        [
            print_metric_series("signal", stats.get("signal"), num_points),
            print_metric_series("remoteSignal", stats.get("remoteSignal"), num_points),
            print_metric_series("signal60g", stats.get("signal60g"), num_points),
            print_metric_series(
                "remoteSignal60g", stats.get("remoteSignal60g"), num_points
            ),
        ]
    )

    if not has_data:
        print("\n  Signal: No data available")


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Fetch signal metrics from UISP devices (active 60GHz devices only)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python get_metrics.py              # Get all active 60GHz devices with signal metrics (last hour)
    python get_metrics.py -n 5         # Limit to first 5 devices
    python get_metrics.py --period 10m   # Get metrics for last 10 minutes
    python get_metrics.py --period 30m   # Get metrics for last 30 minutes
    python get_metrics.py --period 2h    # Get metrics for last 2 hours
    python get_metrics.py --period 7d    # Get metrics for last 7 days
    python get_metrics.py --num-points 10  # Display only 10 data points
    python get_metrics.py --sample-interval 5m  # Sample every 5 minutes
    python get_metrics.py --start 1707580800000  # Specify start time in epoch ms
    python get_metrics.py --list-all   # List all active 60GHz devices with signal
    python get_metrics.py -d "AP-Router"  # Get metrics for specific device by name
    python get_metrics.py -d abc123    # Get metrics for specific device by ID
        """,
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=None,
        help="Limit number of devices to fetch statistics for",
    )
    parser.add_argument(
        "--period",
        type=str,
        default="10m",
        help="Time period for metrics (format: <number><unit>, e.g., 30m, 2h, 7d)",
    )
    parser.add_argument(
        "--num-points",
        type=int,
        default=None,
        help="Number of data points to display (default: all points in the period)",
    )
    parser.add_argument(
        "--sample-interval",
        type=str,
        default="1m",
        help="Sample interval for filtering data points (format: <number><unit>, e.g., 1m, 5m, 10m, 1h)",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=None,
        help="Start time in epoch milliseconds (if not provided, calculated from current time - period)",
    )
    parser.add_argument(
        "--list-all",
        action="store_true",
        help="List all active 60GHz devices with signal and exit (no detailed metrics)",
    )
    parser.add_argument(
        "-d",
        "--device",
        type=str,
        default=None,
        help="Specify device by name or ID (partial match supported)",
    )

    args = parser.parse_args()

    if not UISP_URL:
        print("Error: Missing UISP_URL in .env file")
        return

    if not API_TOKEN:
        print("Error: Missing API_TOKEN in .env file")
        return

    print(f"Using API token for {UISP_URL}...")

    # Step 1: Get devices
    devices = get_devices(API_TOKEN)
    if not devices:
        return

    # If --list-all option, display all devices and exit
    if args.list_all:
        active_devices = [d for d in devices if is_active_60ghz_device(d)]

        print("\n" + "=" * 80)
        print("ACTIVE 60GHz DEVICES WITH SIGNAL")
        print("=" * 80)
        print(
            f"\nTotal active 60GHz devices with signal: {len(active_devices)} (of {len(devices)} total)\n"
        )

        for i, device in enumerate(active_devices, 1):
            info = extract_device_info(device)
            has_60ghz = (
                "Yes"
                if device.get("features", {}).get("has60GhzRadio", False)
                else "No"
            )

            print(f"{i:3d}. {info['name']}")
            print_device_info(info, indent="     ", show_signal=False)
            print(
                f"     Signal: {info.get('signal') or 'N/A'} dBm | 60GHz: {has_60ghz}"
            )
            print()

        print("=" * 80)
        print(f"Total: {len(active_devices)} active 60GHz devices with signal")
        print("=" * 80)
        return

    # Step 2: Filter devices with signal metrics (and optionally by device name/ID)
    devices_with_signals = []

    for device in devices:
        # Only process active devices with signal and 60GHz radio
        if not is_active_60ghz_device(device):
            continue

        # If device filter is specified, check if this device matches
        if args.device and not matches_device_filter(device, args.device.lower()):
            continue

        # Fetch statistics to check if device has any signal metrics
        device_id = device.get("identification", {}).get("id")
        if not device_id:
            continue

        device_name = device.get("identification", {}).get("name", "Unknown")
        stats_data = get_device_statistics(
            API_TOKEN, device_id, args.period, args.start
        )
        stats = extract_statistics(
            stats_data, args.num_points, args.sample_interval, device_name
        )

        # Include device if it has any signal metrics
        if stats and any(
            stats.get(key)
            for key in ["signal", "remoteSignal", "signal60g", "remoteSignal60g"]
        ):
            info = extract_device_info(device)
            devices_with_signals.append((device, info, stats))

            # Stop fetching if we've reached the limit
            if args.limit and len(devices_with_signals) >= args.limit:
                break

    # Step 3: Display devices with signal metrics
    print("\n" + "=" * 60)
    print("ACTIVE 60GHz DEVICES - SIGNAL STRENGTH METRICS")
    print("=" * 60)
    if args.device:
        print(f"\nFiltering by device: '{args.device}'")

    count_msg = (
        f"\nFound {len(devices_with_signals)} active 60GHz devices with signal metrics"
    )
    if args.limit and len(devices_with_signals) >= args.limit:
        count_msg += f" (limited to first {args.limit})"
    print(count_msg)

    if not devices_with_signals:
        print("\nNo active 60GHz devices with signal metrics found.")
        print(f"Total devices checked: {len(devices)}")
        return

    for i, (device, info, stats) in enumerate(devices_with_signals):
        print_signal_metrics(info, stats, args.num_points)

    print(f"\n{'=' * 60}")
    print(
        f"SUMMARY: {len(devices_with_signals)} active 60GHz devices with signal metrics"
    )
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
