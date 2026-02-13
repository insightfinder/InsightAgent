#!/usr/bin/env python3
"""
Send UISP metrics to InsightFinder.

This script:
1. Fetches metrics from UISP devices using get_metrics.py
2. Transforms data to InsightFinder format using transform_metrics.py
3. Sends data to InsightFinder using insightfinder.py

Usage:
    python send_metrics.py                      # Send metrics for all active 60GHz devices (auto-creates project)
    python send_metrics.py --period 10m         # Fetch last 10 minutes of data
    python send_metrics.py --num-points 10      # Limit to 10 data points per device (default: all points)
    python send_metrics.py --no-create-project  # Disable auto-creation of InsightFinder project
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

# Import local modules
from get_metrics import (
    get_device_statistics,
    extract_statistics,
    extract_device_info,
    is_active_60ghz_device,
)
from transform_metrics import transform_all_devices
from insightfinder import InsightFinder, Config

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def format_metrics_for_display(metrics: list[dict[str, str]]) -> list[dict[str, str]]:
    """Format metrics with human-readable timestamps for display.

    NOTE: This function is ONLY used for local debugging/logging.
    The returned metrics are never sent to InsightFinder - only the
    original metrics (without timestamp_readable) are sent.

    Args:
        metrics: List of metric dictionaries with epoch timestamp strings

    Returns:
        List of metrics with added human-readable timestamp field
    """
    formatted = []
    for metric in metrics:
        # Create a copy to avoid modifying original
        display_metric = metric.copy()

        # Add human-readable timestamp
        if "timestamp" in metric:
            try:
                epoch_ms = int(metric["timestamp"])
                human_time = datetime.fromtimestamp(epoch_ms / 1000).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                # Insert readable timestamp right after the epoch timestamp
                display_metric["timestamp_readable"] = human_time
            except (ValueError, OSError):
                display_metric["timestamp_readable"] = "Invalid timestamp"

        formatted.append(display_metric)

    return formatted


def load_config(create_project: bool = False) -> Config:
    """Load InsightFinder configuration from environment variables.

    Args:
        create_project: Whether to auto-create project if it doesn't exist

    Returns:
        Config object

    Raises:
        ValueError: If required environment variables are missing
    """
    # Required variables
    url = os.getenv("INSIGHTFINDER_BASE_URL")
    user_name = os.getenv("INSIGHTFINDER_USER_NAME")
    license_key = os.getenv("INSIGHTFINDER_LICENSE_KEY")
    project_name = os.getenv("INSIGHTFINDER_PROJECT_NAME")

    if not all([url, user_name, license_key, project_name]):
        missing = []
        if not url:
            missing.append("INSIGHTFINDER_BASE_URL")
        if not user_name:
            missing.append("INSIGHTFINDER_USER_NAME")
        if not license_key:
            missing.append("INSIGHTFINDER_LICENSE_KEY")
        if not project_name:
            missing.append("INSIGHTFINDER_PROJECT_NAME")

        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    # Optional variables with defaults
    system_name = os.getenv("INSIGHTFINDER_SYSTEM_NAME", "UISP")
    sampling_interval_minutes = int(os.getenv("INSIGHTFINDER_SAMPLING_INTERVAL", "5"))
    sampling_interval = sampling_interval_minutes * 60  # Convert to seconds

    return Config(
        url=url,
        user_name=user_name,
        license_key=license_key,
        project_name=project_name,
        agent_type="custom",  # For metric streaming
        instance_type="PrivateCloud",
        chunk_size=100000,  # 100KB chunks
        create_project=create_project,
        system_name=system_name,
        data_type="Metric",
        insight_agent_type="Custom",
        samplingInterval=sampling_interval,
    )


def get_device_metrics(
    api_token: str,
    devices: list,
    period: str = "1h",
    num_points: int | None = None,
    sample_interval: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Fetch metrics for all active 60GHz devices.

    Args:
        api_token: UISP API token
        devices: List of devices from UISP API
        period: Time period to fetch (e.g., '10m', '1h', '2h')
        num_points: Number of data points to fetch per device
        sample_interval: Sample interval for filtering (e.g., '1m', '5m')
        limit: Maximum number of devices to process (None for all)

    Returns:
        List of device data with metrics
    """
    # Use sampling interval from env if not specified (in minutes, convert to seconds)
    if sample_interval is None:
        sampling_interval_minutes = int(
            os.getenv("INSIGHTFINDER_SAMPLING_INTERVAL", "5")
        )
        sampling_interval_seconds = sampling_interval_minutes * 60
        if sampling_interval_seconds >= 3600:
            sample_interval = f"{sampling_interval_seconds // 3600}h"
        else:
            sample_interval = f"{sampling_interval_seconds // 60}m"

    devices_with_metrics = []

    for device in devices:
        # Only process active devices with signal and 60GHz radio
        if not is_active_60ghz_device(device):
            continue

        device_id = device.get("identification", {}).get("id")
        if not device_id:
            continue

        # Fetch statistics
        logger.debug(
            f"Fetching metrics for device: {device.get('identification', {}).get('name', 'Unknown')}"
        )
        stats_data = get_device_statistics(api_token, device_id, period)

        if not stats_data:
            logger.warning(f"No statistics data for device {device_id}")
            continue

        device_name = device.get("identification", {}).get("name", "Unknown")
        stats = extract_statistics(stats_data, num_points, sample_interval, device_name)

        # Include device if it has any signal metrics
        if stats and any(
            stats.get(key)
            for key in ["signal", "remoteSignal", "signal60g", "remoteSignal60g"]
        ):
            info = extract_device_info(device)

            # Count total data points for this device
            total_points = sum(len(v) for v in stats.values() if v is not None)
            logger.debug(
                f"{device_name}: {total_points} data points ready for transformation"
            )

            # Merge device info with metrics
            device_entry = {**info, **stats}
            devices_with_metrics.append(device_entry)

            # Stop if we've reached the limit
            if limit and len(devices_with_metrics) >= limit:
                logger.info(f"Reached device limit of {limit}")
                break

    logger.info(f"Found {len(devices_with_metrics)} devices with metrics")
    return devices_with_metrics


def send_to_insightfinder(
    insightfinder: InsightFinder,
    devices_metrics: dict[str, Any],
    verbose: bool = False,
) -> None:
    """Send metrics to InsightFinder using v2 API (batched).

    Args:
        insightfinder: InsightFinder client instance
        devices_metrics: Instance data map (idm) with all devices in v2 format
        verbose: Whether to output detailed payload information
    """
    if not devices_metrics:
        logger.warning("No device metrics to send")
        return

    num_devices = len(devices_metrics)

    try:
        logger.info(f"Sending metrics for {num_devices} device(s) in batched request")

        if verbose:
            config = insightfinder.config
            logger.debug(f"\n{'─' * 60}")
            logger.debug("API Call Parameters:")
            logger.debug(f"{'─' * 60}")
            logger.debug(f"Endpoint: {config.url}/api/v2/metric-data-receive")
            logger.debug(f"Project Name: {config.project_name}")
            logger.debug(f"User Name: {config.user_name}")
            logger.debug(f"Agent Type (iat): {config.agent_type}")
            logger.debug(f"Instance Type (ct): {config.instance_type}")
            logger.debug(f"Number of Instances: {num_devices}")

            # Count total data points across all devices
            total_points = 0
            for instance_name, instance_data in devices_metrics.items():
                dit = instance_data.get("dit", {})
                total_points += len(dit)
                logger.debug(f"  - {instance_name}: {len(dit)} timestamp(s)")

            logger.debug(f"\nTotal timestamps across all devices: {total_points}")
            logger.debug("\nPayload structure (idm):")
            logger.debug(json.dumps(devices_metrics, indent=2))
            logger.debug(f"{'─' * 60}\n")

        # Send all devices in single batched request
        insightfinder.send_metric(devices_metrics)

        logger.info(f"✓ Successfully sent metrics for {num_devices} device(s)")

    except Exception as e:
        logger.error(f"✗ Failed to send metrics: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Send UISP metrics to InsightFinder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python send_metrics.py                    # Send all metrics with default settings
    python send_metrics.py -n 5               # Limit to first 5 devices
    python send_metrics.py --period 10m       # Fetch last 10 minutes
    python send_metrics.py --period 1h        # Fetch last hour
    python send_metrics.py --num-points 10     # Limit to 10 data points per device
    python send_metrics.py --sample-interval 5m  # Sample every 5 minutes
    python send_metrics.py --no-create-project # Disable auto-creation of project
    python send_metrics.py --dry-run          # Test without sending to InsightFinder
        """,
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=None,
        help="Limit number of devices to process (default: all devices)",
    )
    parser.add_argument(
        "--period",
        type=str,
        default="1h",
        help="Time period for metrics (format: <number><unit>, e.g., 10m, 1h, 2h, 7d)",
    )
    parser.add_argument(
        "--num-points",
        type=int,
        default=None,
        help="Number of data points to fetch per device (default: all points in the period)",
    )
    parser.add_argument(
        "--sample-interval",
        type=str,
        default=None,
        help="Sample interval for filtering data points (default: from INSIGHTFINDER_SAMPLING_INTERVAL in .env)",
    )
    parser.add_argument(
        "--create-project",
        action="store_true",
        default=True,
        help="Auto-create InsightFinder project if it doesn't exist (default: enabled)",
    )
    parser.add_argument(
        "--no-create-project",
        action="store_false",
        dest="create_project",
        help="Disable auto-creation of InsightFinder project",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and transform data but don't send to InsightFinder",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging and show payloads when sending metrics",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load UISP configuration
    uisp_url = os.getenv("UISP_URL")
    api_token = os.getenv("UISP_API_TOKEN") or os.getenv("API_TOKEN")

    if not uisp_url:
        logger.error("Missing UISP_URL in .env file")
        sys.exit(1)

    if not api_token:
        logger.error("Missing UISP_API_TOKEN or API_TOKEN in .env file")
        sys.exit(1)

    logger.info(f"Using UISP URL: {uisp_url}")

    # Step 1: Fetch devices from UISP
    logger.info("\n" + "=" * 60)
    logger.info("STEP 1: Fetching devices from UISP")
    logger.info("=" * 60)

    from get_metrics import get_devices as fetch_devices

    devices = fetch_devices(api_token)

    if not devices:
        logger.error("No devices found")
        sys.exit(1)

    # Step 2: Fetch metrics for devices
    logger.info("\n" + "=" * 60)
    logger.info("STEP 2: Fetching metrics for active 60GHz devices")
    if args.limit:
        logger.info(f"Limiting to first {args.limit} devices")
    logger.info("=" * 60)

    devices_with_metrics = get_device_metrics(
        api_token,
        devices,
        period=args.period,
        num_points=args.num_points,
        sample_interval=args.sample_interval,
        limit=args.limit,
    )

    if not devices_with_metrics:
        logger.warning("No devices with metrics found")
        sys.exit(0)

    # Step 3: Transform metrics to InsightFinder format
    logger.info("\n" + "=" * 60)
    logger.info("STEP 3: Transforming metrics to InsightFinder format")
    logger.info("=" * 60)

    transformed_metrics = transform_all_devices(devices_with_metrics)

    logger.info(f"Transformed metrics for {len(transformed_metrics)} devices")

    # Log detailed data point counts per device
    for device_name, instance_data in transformed_metrics.items():
        dit = instance_data.get("dit", {})
        logger.debug(f"{device_name}: {len(dit)} timestamp(s) ready to send")

    # Log sample data for first device (if verbose)
    if args.verbose and transformed_metrics:
        first_device = next(iter(transformed_metrics.keys()))
        instance_data = transformed_metrics[first_device]
        dit = instance_data.get("dit", {})
        logger.debug(f"\nSample data for {first_device}:")
        logger.debug(f"  Instance name: {instance_data.get('in')}")
        logger.debug(f"  Total timestamps: {len(dit)}")
        if dit:
            first_timestamp = next(iter(dit.keys()))
            first_entry = dit[first_timestamp]
            logger.debug(f"  First timestamp: {first_timestamp}")
            logger.debug(f"  Metrics: {json.dumps(first_entry, indent=4)}")

    # Step 4: Send metrics to InsightFinder
    if args.dry_run:
        logger.info("\n" + "=" * 60)
        logger.info("DRY RUN: Skipping send to InsightFinder")
        logger.info("=" * 60)
        logger.info(
            f"Would send metrics for {len(transformed_metrics)} devices in batched request:"
        )

        # Display summary for each device
        for device_name, instance_data in transformed_metrics.items():
            dit = instance_data.get("dit", {})
            logger.info(f"\n{'─' * 60}")
            logger.info(f"Device: {device_name}")
            logger.info(f"Instance name: {instance_data.get('in')}")
            logger.info(f"Timestamps: {len(dit)}")
            logger.info(f"{'─' * 60}")

        # Display full idm payload structure
        logger.info(f"\n{'─' * 60}")
        logger.info("Full payload (idm structure):")
        logger.info(f"{'─' * 60}")
        payload = json.dumps(transformed_metrics, indent=2)
        logger.info(f"{payload}")

    else:
        logger.info("\n" + "=" * 60)
        logger.info("STEP 4: Sending metrics to InsightFinder")
        logger.info("=" * 60)

        try:
            # Load InsightFinder configuration
            config = load_config(create_project=args.create_project)
            logger.info(f"InsightFinder project: {config.project_name}")

            # Create InsightFinder client
            insightfinder = InsightFinder(config)

            # Send metrics
            send_to_insightfinder(
                insightfinder, transformed_metrics, verbose=args.verbose
            )

        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to send metrics: {e}", exc_info=args.verbose)
            sys.exit(1)

    logger.info("\nDone!")


if __name__ == "__main__":
    main()
