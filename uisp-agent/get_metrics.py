#!/usr/bin/env python3
"""
UISP Device Metrics Fetcher
Fetches device overview metrics from UISP devices.

Supported Metrics by Device Type:
  - airFiber (PTP/PTMP): signal, downlinkUtilization, uplinkUtilization, linkActiveStationsCount
  - airMax (WiFi AP): signal, downlinkUtilization, uplinkUtilization, linkActiveStationsCount
  - OLT (Fiber): stationsCount (ONUs)
  - ONU (Fiber): signal, receivePower

Usage:
    python get_metrics.py              # Get all devices with their metrics
    python get_metrics.py -n 5         # Limit to first 5 devices
    python get_metrics.py -d "device-name"  # Get specific device by name
"""

import argparse
import logging
import os
import sys
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


def get_devices(token):
    """Get list of all devices."""
    url = f"{BASE_API}/devices"
    headers = {"x-auth-token": token}

    print("\nFetching devices...")
    response = requests.get(url, headers=headers, verify=False)

    if response.status_code == 200:
        devices = response.json()
        print(f"✓ Found {len(devices)} total devices")
        return devices
    else:
        print(f"✗ Failed to fetch devices: {response.status_code}")
        return []


def get_device_detail(token, device_id):
    """Fetch full device details including ONU info and station data.
    
    Args:
        token: UISP API token
        device_id: Device ID
        
    Returns:
        Device detail object or None if fetch fails
    """
    url = f"{BASE_API}/devices/{device_id}/detail?withStations=true"
    headers = {"x-auth-token": token}
    
    try:
        response = requests.get(url, headers=headers, verify=False)
        if response.status_code == 200:
            return response.json()
        else:
            logger.debug(f"Failed to fetch detail for device {device_id}: {response.status_code}")
            return None
    except Exception as e:
        logger.debug(f"Error fetching detail for device {device_id}: {e}")
        return None


def extract_device_metrics(device):
    """Extract metrics from device overview data.
    
    Returns dict with device info and applicable metrics based on device type.
    """
    identification = device.get("identification", {})
    overview = device.get("overview", {})
    device_type = identification.get("type", "unknown")
    
    metrics = {
        "id": identification.get("id", ""),
        "name": identification.get("name", "Unknown"),
        "model": identification.get("model", ""),
        "type": device_type,
        "role": identification.get("role", ""),
        "status": overview.get("status", ""),
    }
    
    # Get site name
    site_info = identification.get("site")
    metrics["site"] = site_info.get("name", "") if site_info else ""
    
    # Get IP address (remove CIDR notation like /16)
    ip_address = device.get("ipAddress", "")
    if ip_address and "/" in ip_address:
        ip_address = ip_address.split("/")[0]
    metrics["ipAddress"] = ip_address
    
    # Extract metrics based on device type
    if device_type in ["airFiber", "airMax"]:
        # Wireless devices (PTP/PTMP/WiFi AP)
        metrics["signal"] = overview.get("signal")
        metrics["downlinkUtilization"] = overview.get("downlinkUtilization")
        metrics["uplinkUtilization"] = overview.get("uplinkUtilization")
        metrics["linkActiveStationsCount"] = overview.get("linkActiveStationsCount")
        
        # Per-station capacity metrics
        metrics["stations"] = extract_station_metrics(device)
        
    elif device_type == "olt":
        # Fiber OLT (access point)
        metrics["stationsCount"] = overview.get("stationsCount")  # ONUs connected
        
    elif device_type == "onu":
        # Fiber ONU (client)
        metrics["signal"] = overview.get("signal")  # Optical signal strength  
        onu_data = device.get("onu", {})
        metrics["receivePower"] = onu_data.get("receivePower")
        metrics["rxRate"] = onu_data.get("rxRate")  # Receive bit rate
        metrics["txRate"] = onu_data.get("txRate")  # Transmit bit rate
        
        # Debug logging
        if not onu_data:
            logger.debug(f"ONU device {metrics['name']}: No 'onu' object in device data")
        else:
            logger.debug(f"ONU device {metrics['name']}: receivePower={metrics['receivePower']}, rxRate={metrics['rxRate']}, txRate={metrics['txRate']}")
    
    return metrics


def extract_station_metrics(device):
    """Extract per-station capacity metrics from wireless devices.
    
    Args:
        device: Device object from UISP API
        
    Returns:
        List of station metrics with downlinkCapacity, uplinkCapacity, txMcs, rxMcs
    """
    stations = []
    interfaces = device.get("interfaces", [])
    
    for interface in interfaces:
        # Look for wireless interfaces
        if interface.get("identification", {}).get("type") != "wlan":
            continue
        
        # Extract per-station metrics (stations can be None or a list)
        interface_stations = interface.get("stations") or []
        for station in interface_stations:
            station_data = {
                "name": station.get("name", ""),
                "mac": station.get("mac", ""),
                "downlinkCapacity": station.get("downlinkCapacity"),
                "uplinkCapacity": station.get("uplinkCapacity"),
                "txMcs": station.get("txMcs"),
                "rxMcs": station.get("rxMcs"),
            }
            stations.append(station_data)
    
    return stations if stations else None


def matches_device_filter(device, search_term):
    """Check if device matches the search filter."""
    identification = device.get("identification", {})
    device_name = (identification.get("name") or "").lower()
    device_id = (identification.get("id") or "").lower()
    return search_term in device_name or search_term in device_id


def print_device_metrics(metrics, verbose=False):
    """Print device metrics."""
    print(f"\n{'=' * 70}")
    print(f"Device: {metrics['name']}")
    print(f"{'=' * 70}")
    print(f"  ID: {metrics['id']}")
    print(f"  Type: {metrics['type']} | Role: {metrics['role']}")
    print(f"  Model: {metrics['model']}")
    print(f"  Site: {metrics['site']}")
    print(f"  Status: {metrics['status']}")
    
    # Print type-specific metrics
    if metrics['type'] in ["airFiber", "airMax"]:
        print(f"\n  Metrics:")
        print(f"    Signal: {metrics.get('signal')} dBm" if metrics.get('signal') is not None else f"    Signal: N/A")
        print(f"    Downlink Utilization: {metrics.get('downlinkUtilization')}")
        print(f"    Uplink Utilization: {metrics.get('uplinkUtilization')}")
        print(f"    Active Stations: {metrics.get('linkActiveStationsCount')}")
        
        # Print per-station metrics if available and verbose
        if verbose and metrics.get('stations'):
            print(f"\n  Connected Stations ({len(metrics['stations'])}):")
            for station in metrics['stations']:
                print(f"    - {station['name']} ({station['mac']})")
                print(f"      DL Capacity: {station.get('downlinkCapacity')} bps")
                print(f"      UL Capacity: {station.get('uplinkCapacity')} bps")
                print(f"      TX MCS: {station.get('txMcs')} | RX MCS: {station.get('rxMcs')}")
    
    elif metrics['type'] == "olt":
        print(f"\n  Metrics:")
        print(f"    Connected ONUs: {metrics.get('stationsCount')}")
    
    elif metrics['type'] == "onu":
        print(f"\n  Metrics:")
        signal = metrics.get('signal')
        rx_power = metrics.get('receivePower')
        print(f"    Signal: {signal} dBm" if signal is not None else f"    Signal: N/A")
        print(f"    RX Power: {rx_power} dBm" if rx_power is not None else f"    RX Power: N/A")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch device metrics from UISP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python get_metrics.py                  # Get all devices with metrics
    python get_metrics.py -n 5             # Limit to first 5 devices
    python get_metrics.py -d "device-name" # Get specific device by name
    python get_metrics.py -v               # Verbose output (show per-station details)
        """,
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=None,
        help="Limit number of devices to display",
    )
    parser.add_argument(
        "-d",
        "--device",
        type=str,
        default=None,
        help="Filter by device name or ID (partial match)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed per-station metrics",
    )

    args = parser.parse_args()

    if not UISP_URL:
        print("✗ Error: UISP_URL not set in .env file")
        sys.exit(1)

    if not API_TOKEN:
        print("✗ Error: API_TOKEN or UISP_API_TOKEN not set in .env file")
        sys.exit(1)

    print(f"Using UISP URL: {UISP_URL}")

    # Fetch devices
    devices = get_devices(API_TOKEN)
    if not devices:
        sys.exit(1)

    # Extract metrics for all active devices
    devices_metrics = []
    for device in devices:
        overview = device.get("overview", {})
        if overview.get("status", "").lower() == "active":
            metrics = extract_device_metrics(device)
            devices_metrics.append(metrics)

    # Filter by device name/ID if specified
    if args.device:
        search_term = args.device.lower()
        devices_metrics = [
            d for d in devices_metrics
            if search_term in d["name"].lower() or search_term in d["id"].lower()
        ]

    # Apply limit
    if args.limit:
        devices_metrics = devices_metrics[: args.limit]

    # Display results
    print("\n" + "=" * 70)
    print(f"ACTIVE DEVICES - METRICS OVERVIEW")
    print("=" * 70)
    print(f"Found {len(devices_metrics)} active device(s)")

    if not devices_metrics:
        print("No active devices found")
        sys.exit(0)

    for metrics in devices_metrics:
        print_device_metrics(metrics, verbose=args.verbose)

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {len(devices_metrics)} active device(s)")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
