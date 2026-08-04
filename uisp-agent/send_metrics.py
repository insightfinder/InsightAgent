#!/usr/bin/env python3
"""
Send UISP metrics to InsightFinder.

This script:
1. Fetches device overview metrics from UISP devices
2. Transforms data to InsightFinder format
3. Sends data to InsightFinder

Supported Metrics:
  - airFiber/airMax: signal, downlink/uplink utilization, active stations count, per-station capacity
  - OLT: ONU count
  - ONU: signal, receive power

Usage:
    python send_metrics.py                      # Send metrics for all active devices
    python send_metrics.py -n 5                 # Limit to 5 devices
    python send_metrics.py --no-create-project  # Disable auto-creation of InsightFinder project
    python send_metrics.py --dry-run            # Test without sending
    python send_metrics.py -v                   # Verbose output
"""

import argparse
import datetime
import json
import logging
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import urllib3
from dotenv import load_dotenv

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Import local modules
from get_metrics import extract_device_metrics, get_devices
from transform_metrics import transform_all_devices
from insightfinder import InsightFinder, Config
from device_inventory_lookup import resolve_device, atomic_write_json

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DEVICE_LOOKUP_PATH = Path(__file__).parent / "devicelookup.json"
DEVICE_NOT_FOUND_PATH = Path(__file__).parent / "devicelookupnotfound.json"
DEVICE_INVENTORY_SCRIPT = Path(__file__).parent / "device_inventory_lookup.py"


def load_device_lookup(path: Path = DEVICE_LOOKUP_PATH) -> dict:
    try:
        data = json.loads(path.read_text())
        return {k: v for k, v in data.items() if k != "lastmodifiedtimedata"}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def load_device_not_found(path: Path = DEVICE_NOT_FOUND_PATH) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def load_lastmodified(path: Path = DEVICE_LOOKUP_PATH) -> str:
    try:
        return json.loads(path.read_text()).get("lastmodifiedtimedata", "")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return ""


def maybe_refresh_device_lookup() -> bool:
    """Run device_inventory_lookup.py once per day during the 00:00-00:20 UTC
    window. Reads lastmodifiedtimedata from devicelookup.json to skip if
    already run today. Never raises. Returns True if a refresh was executed."""
    now = datetime.datetime.now(datetime.timezone.utc)
    if not (now.hour == 0 and now.minute < 20):
        return False
    ts = load_lastmodified()
    if ts:
        try:
            if datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").date() == now.date():
                return False  # already refreshed today
        except ValueError:
            pass
    logger.info("Device inventory refresh triggered (00:00-00:20 UTC window).")
    try:
        subprocess.run(
            [sys.executable, str(DEVICE_INVENTORY_SCRIPT)],
            timeout=600,
            check=False,
            capture_output=True,
        )
    except Exception as exc:
        logger.warning(f"Device inventory refresh failed (ignored): {exc}")
    return True


def resolve_new_devices(
    devices: list[dict], device_lookup: dict, device_not_found: dict,
    base_url: str, api_key: str,
) -> set[str]:
    """Look up any device seen for the first time immediately, rather than
    waiting for the once-daily inventory refresh window - a device seen for
    the first time must be looked up right away, not stream under its bare
    own name until the next scheduled refresh happens to come around.
    Mutates device_lookup/device_not_found in place and persists both files
    if anything changed.

    Returns the set of macs that errored this cycle (API/network error, so no
    conclusive answer yet) - the caller MUST exclude these from this run's
    transform rather than falling back to their own name: a device that has
    never actually been through a completed Inventory lookup is not the same
    as one Inventory has confirmed it doesn't have, and must not be sent under
    any identity until an actual lookup attempt resolves it one way or the
    other."""
    seen: set[str] = set()
    pending: set[str] = set()
    changed = False
    for device in devices:
        mac = (device.get("mac") or "").lower()
        if not mac or mac in seen or mac in device_lookup or mac in device_not_found:
            continue
        seen.add(mac)
        device_stub = {
            "mac": mac,
            "serialNumber": device.get("serialNumber") or "",
            "name": device.get("name") or "",
            "ip": device.get("ipAddress") or "",
        }
        device_key, matched_entry, had_error = resolve_device(device_stub, base_url, api_key)
        if had_error:
            pending.add(mac)
            logger.warning(f"Inventory: API error resolving new device {mac} - will retry next run")
            continue
        if matched_entry:
            device_lookup[device_key] = matched_entry
            logger.info(f"Inventory: resolved new device {mac} via {matched_entry['identifier_used']!r}")
        else:
            device_not_found[device_key] = {"device": device_stub}
            logger.info(f"Inventory: new device {mac} not found in Inventory")
        changed = True

    if changed:
        # Preserve whatever full-refresh timestamp is currently on disk -
        # incremental saves must never advance it, or the once-daily full
        # refresh (which revalidates existing matches and retries misses)
        # would never fire again today.
        payload = dict(device_lookup)
        last_modified = load_lastmodified()
        if last_modified:
            payload["lastmodifiedtimedata"] = last_modified
        atomic_write_json(DEVICE_LOOKUP_PATH, payload)
        atomic_write_json(DEVICE_NOT_FOUND_PATH, device_not_found)

    return pending


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


def get_device_overview_metrics(
    api_token: str,
    devices: list,
    limit: int | None = None,
) -> list[dict]:
    """Fetch overview metrics for all active devices using concurrent requests.

    Args:
        api_token: UISP API token
        devices: List of devices from UISP API
        limit: Maximum number of devices to process (None for all)

    Returns:
        List of device data with metrics
    """
    uisp_url = os.getenv("UISP_URL", "").rstrip("/")
    base_api = f"{uisp_url}/nms/api/v2.1"
    max_workers = int(os.getenv("UISP_MAX_WORKERS", "3"))
    timeout = int(os.getenv("UISP_TIMEOUT", "30"))
    
    # Filter active devices
    active_devices = []
    for device in devices:
        overview = device.get("overview", {})
        if overview.get("status", "").lower() != "active":
            continue
        device_id = device.get("identification", {}).get("id")
        if not device_id:
            continue
        active_devices.append(device)
        if limit and len(active_devices) >= limit:
            break
    
    logger.info(f"Fetching details for {len(active_devices)} active devices (max {max_workers} concurrent)")
    
    devices_with_metrics = []
    
    def fetch_device_detail(device):
        """Fetch and extract metrics for a single device."""
        device_id = device.get("identification", {}).get("id")
        device_name = device.get("identification", {}).get("name", "unknown")
        
        try:
            url = f"{base_api}/devices/{device_id}/detail?withStations=true"
            headers = {"x-auth-token": api_token}
            response = requests.get(url, headers=headers, verify=False, timeout=timeout)
            
            if response.status_code != 200:
                logger.debug(f"Could not fetch detail for {device_name}: {response.status_code}")
                return None
            
            device_detail = response.json()
            metrics = extract_device_metrics(device_detail)
            return metrics
        except Exception as e:
            logger.debug(f"Error fetching detail for {device_name}: {e}")
            return None
    
    # Use ThreadPoolExecutor for concurrent requests
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(fetch_device_detail, device): device 
            for device in active_devices
        }
        
        # Collect results as they complete
        completed = 0
        for future in as_completed(futures):
            completed += 1
            result = future.result()
            if result:
                devices_with_metrics.append(result)
            
            # Log progress every 50 devices
            if completed % 50 == 0:
                logger.info(f"  Progress: {completed}/{len(active_devices)} devices fetched ({len(devices_with_metrics)} with metrics)")
    
    logger.info(f"Found {len(devices_with_metrics)} active devices with metrics")
    return devices_with_metrics


def send_to_insightfinder(
    insightfinder: InsightFinder,
    devices_metrics: dict[str, dict],
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

            # Count total metrics across all devices
            total_metrics = 0
            for instance_name, instance_data in devices_metrics.items():
                dit = instance_data.get("dit", {})
                for ts_data in dit.values():
                    total_metrics += len(ts_data.get("metricDataPointSet", []))

            logger.debug(f"\nTotal metrics across all devices: {total_metrics}")
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
        description="Send UISP device metrics to InsightFinder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python send_metrics.py                    # Send all metrics with default settings
    python send_metrics.py -n 5               # Limit to first 5 devices
    python send_metrics.py --no-create-project # Disable auto-creation of project
    python send_metrics.py --dry-run          # Test without sending to InsightFinder
    python send_metrics.py -v                 # Verbose output
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
        help="Enable debug logging and show payloads",
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

    # Device Inventory (Asset Registry) enrichment - leave both blank to disable.
    inv_base_url = os.getenv("JIRAASSET_BASE")
    inv_api_key = os.getenv("JIRAASSET_API_KEY")
    if not (inv_base_url and inv_api_key):
        logger.warning("JIRAASSET_BASE/JIRAASSET_API_KEY not set - Inventory enrichment disabled.")

    logger.info(f"Using UISP URL: {uisp_url}")

    # Step 1: Fetch devices from UISP
    logger.info("\n" + "=" * 60)
    logger.info("STEP 1: Fetching devices from UISP")
    logger.info("=" * 60)

    devices = get_devices(api_token)

    if not devices:
        logger.error("No devices found")
        sys.exit(1)

    # Step 2: Fetch metrics for devices
    logger.info("\n" + "=" * 60)
    logger.info("STEP 2: Extracting metrics for active devices")
    if args.limit:
        logger.info(f"Limiting to first {args.limit} devices")
    logger.info("=" * 60)

    devices_with_metrics = get_device_overview_metrics(
        api_token,
        devices,
        limit=args.limit,
    )

    if not devices_with_metrics:
        logger.warning("No devices with metrics found")
        sys.exit(0)

    # Step 2b: Device Inventory enrichment
    device_lookup: dict = {}
    if inv_base_url and inv_api_key:
        logger.info("\n" + "=" * 60)
        logger.info("STEP 2b: Device Inventory lookup")
        logger.info("=" * 60)

        if maybe_refresh_device_lookup():
            logger.info("Full Inventory refresh completed for today.")

        device_lookup = load_device_lookup()
        device_not_found = load_device_not_found()
        logger.info(f"Loaded {len(device_lookup)} matched / {len(device_not_found)} not-found Inventory entries")

        # Resolve any device seen for the first time immediately, rather than
        # waiting for the once-daily inventory refresh window above.
        pending = resolve_new_devices(devices_with_metrics, device_lookup, device_not_found, inv_base_url, inv_api_key)

        if pending:
            # Never seen a completed lookup (API error, not a confirmed
            # miss) - exclude entirely rather than sending under its own
            # name; it'll be retried next run.
            before = len(devices_with_metrics)
            devices_with_metrics = [d for d in devices_with_metrics if (d.get("mac") or "").lower() not in pending]
            logger.warning(
                f"Excluding {before - len(devices_with_metrics)} device(s) still pending "
                f"Inventory resolution - will retry next run"
            )

    # Step 3: Transform metrics to InsightFinder format
    logger.info("\n" + "=" * 60)
    logger.info("STEP 3: Transforming metrics to InsightFinder format")
    logger.info("=" * 60)

    transformed_metrics = transform_all_devices(devices_with_metrics, device_lookup)

    logger.info(f"Transformed metrics for {len(transformed_metrics)} devices")

    # Log device breakdown by type
    type_counts = {}
    for device in devices_with_metrics:
        dtype = device.get("type", "unknown")
        type_counts[dtype] = type_counts.get(dtype, 0) + 1

    for dtype, count in sorted(type_counts.items()):
        logger.info(f"  - {dtype}: {count} device(s)")

    # Step 4: Send metrics to InsightFinder
    if args.dry_run:
        logger.info("\n" + "=" * 60)
        logger.info("DRY RUN: Skipping send to InsightFinder")
        logger.info("=" * 60)
        logger.info(
            f"Would send metrics for {len(transformed_metrics)} devices in batched request"
        )

        # Display summary for each device
        for device_name, instance_data in transformed_metrics.items():
            dit = instance_data.get("dit", {})
            for ts_str, ts_data in dit.items():
                metrics = ts_data.get("metricDataPointSet", [])
                logger.info(f"\n{'─' * 60}")
                logger.info(f"Device: {device_name}")
                logger.info(f"Timestamp: {ts_str}")
                logger.info(f"Metrics: {len(metrics)}")
                for metric in metrics:
                    logger.info(f"  - {metric['m']}: {metric['v']}")
                logger.info(f"{'─' * 60}")

        # Display full idm payload structure if verbose
        if args.verbose:
            logger.debug(f"\n{'─' * 60}")
            logger.debug("Full payload (idm structure):")
            logger.debug(f"{'─' * 60}")
            payload = json.dumps(transformed_metrics, indent=2)
            logger.debug(f"{payload}")

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
