#!/usr/bin/env python3

"""
Get CPE signal metrics (RSRP, RSRQ, SINR, CINR) at regular intervals.

Usage:
    python3 get_metrics.py [serial_number] [options]

Examples:
    # Poll a specific CPE every 1 minute for 10 iterations
    python3 get_metrics.py CPE123456 --interval 60 --iterations 10

    # Poll all available CPE devices every 30 seconds
    python3 get_metrics.py --interval 30

    # Poll first 5 available CPE devices indefinitely
    python3 get_metrics.py --devices 5 --interval 60
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from baicells_client import BaiCellsClient

logger = logging.getLogger(__name__)

DEFAULT_DEVICE_FILE = "cpe-device-sn.txt"


def add_device_args(parser: argparse.ArgumentParser) -> None:
    """Add shared device-selection and polling arguments to an argument parser."""
    parser.add_argument(
        "serial_number",
        nargs="?",
        default=None,
        help="CPE serial number (if not provided, reads from file or discovers all CPEs)",
    )
    parser.add_argument(
        "-f",
        "--file",
        type=str,
        default=None,
        help="File containing CPE serial numbers (one per line)",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=None,
        help="Polling interval in seconds (default: 60, or INSIGHTFINDER_SAMPLING_INTERVAL from .env for send_metrics.py)",
    )
    parser.add_argument(
        "-n",
        "--iterations",
        type=int,
        default=None,
        help="Maximum number of polling iterations (default: infinite)",
    )
    parser.add_argument(
        "-d",
        "--devices",
        type=int,
        default=None,
        help="Maximum number of CPE devices to monitor (default: all)",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="BaiCells API base URL (overrides .env)",
    )
    parser.add_argument(
        "--username",
        default=None,
        help="API username (overrides .env)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="API password (overrides .env)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )


def resolve_serial_numbers(
    args: argparse.Namespace, client: BaiCellsClient
) -> list[str]:
    """Resolve the list of CPE serial numbers to monitor based on parsed args.

    Priority: explicit serial > --file > DEFAULT_DEVICE_FILE > auto-discover online CPEs.

    Args:
        args: Parsed argparse namespace (must have serial_number, file, devices attributes)
        client: Authenticated BaiCellsClient instance

    Returns:
        List of serial number strings

    Raises:
        SystemExit: On unrecoverable errors (missing file, no devices found, etc.)
    """
    if args.serial_number and args.file:
        logger.error("Cannot specify both serial number and file.")
        sys.exit(1)

    if args.serial_number:
        return [args.serial_number]

    file_path = args.file or DEFAULT_DEVICE_FILE
    is_explicit_file = bool(args.file)

    # Try reading from file (explicit --file, or the default cpe-device-sn.txt)
    try:
        logger.info(f"Reading serial numbers from {file_path}...")
        with open(file_path, "r") as f:
            serial_numbers = [
                line.strip()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            ]

        if not serial_numbers:
            if is_explicit_file:
                logger.warning(f"No serial numbers found in {file_path}.")
                sys.exit(1)
            # Fall through to auto-discover if default file is empty
        else:
            logger.info(f"Found {len(serial_numbers)} serial number(s) in file.")
            if args.devices and args.devices > 0:
                serial_numbers = serial_numbers[: args.devices]
                logger.info(f"Limited to first {len(serial_numbers)} device(s).")
            return serial_numbers

    except FileNotFoundError:
        if is_explicit_file:
            logger.error(f"File '{file_path}' not found.")
            sys.exit(1)
        # Default file not found — fall through to auto-discover
    except Exception as e:
        logger.error(f"Error reading file '{file_path}': {e}")
        sys.exit(1)

    # Auto-discover all online CPE devices
    logger.info("Querying all available CPE devices...")
    result = client.get_all_cpes()
    all_cpes = result["all_devices"]

    if not all_cpes:
        logger.warning("No CPE devices found.")
        sys.exit(1)

    online_cpes = [
        device
        for device in all_cpes
        if device.get("connection_status", "").lower() == "on"
    ]

    if not online_cpes:
        logger.warning(f"Found {len(all_cpes)} CPE device(s), but none are online.")
        sys.exit(1)

    if args.devices and args.devices > 0:
        online_cpes = online_cpes[: args.devices]

    serial_numbers = [
        device.get("serial_number")
        for device in online_cpes
        if device.get("serial_number")
    ]

    if not serial_numbers:
        logger.warning("No valid serial numbers found in online CPE devices.")
        sys.exit(1)

    logger.info(f"Found {len(serial_numbers)} online CPE device(s) to monitor.")
    return serial_numbers


def poll_metrics(
    client: BaiCellsClient,
    serial_numbers: list[str],
    interval_seconds: int = 60,
    max_iterations: int | None = None,
):
    """
    Poll CPE signal metrics at regular intervals and print them.

    Args:
        client: BaiCellsClient instance
        serial_numbers: List of CPE serial numbers to monitor
        interval_seconds: Polling interval in seconds (default: 60)
        max_iterations: Maximum number of polls (None = infinite)
    """
    device_count = len(serial_numbers)
    logger.info(f"Starting CPE metrics polling for {device_count} device(s)")
    logger.info(
        f"Devices: {', '.join(serial_numbers[:3])}{'...' if device_count > 3 else ''}"
    )
    logger.info(f"Interval: {interval_seconds}s")
    if max_iterations:
        logger.info(f"Max iterations: {max_iterations}")

    BATCH_SIZE = 20
    batches = [
        serial_numbers[i : i + BATCH_SIZE] for i in range(0, device_count, BATCH_SIZE)
    ]
    start_time = time.time()
    iteration = 0

    try:
        while True:
            for batch_idx, batch in enumerate(batches):
                batch_start = time.time()
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                batch_offset = batch_idx * BATCH_SIZE

                for idx, serial_number in enumerate(batch, batch_offset + 1):
                    logger.info(
                        f"[{idx}/{device_count}] Fetching metrics for {serial_number}"
                    )
                    try:
                        cpe_info = client.get_cpe_info(serial_number)

                        rsrp0 = cpe_info.get("rsrp0", "N/A")
                        rsrp1 = cpe_info.get("rsrp1", "N/A")
                        sinr = cpe_info.get("cpeSinr", "N/A")
                        cinr0 = cpe_info.get("cinr0", "N/A")
                        cinr1 = cpe_info.get("cinr1", "N/A")
                        status = cpe_info.get("connectionStatus", "N/A")

                        logger.info(
                            f"{timestamp:<20} {serial_number:<25} {str(rsrp0):<10} {str(rsrp1):<10} {str(sinr):<10} "
                            f"{str(cinr0):<10} {str(cinr1):<10} {str(status):<12}"
                        )

                        nr_rsrp = cpe_info.get("nrRsrp")
                        nr_rsrq = cpe_info.get("nrRsrq")
                        nr_sinr = cpe_info.get("nrSinr")
                        if any([nr_rsrp, nr_rsrq, nr_sinr]):
                            logger.info(
                                f"  └─ 5G NR: RSRP={nr_rsrp}, RSRQ={nr_rsrq}, SINR={nr_sinr}"
                            )

                    except Exception as e:
                        logger.error(f"{timestamp:<20} {serial_number:<25} ERROR: {e}")

                # Sleep only the time remaining in the 60s window before the next batch
                if batch_idx < len(batches) - 1:
                    elapsed = time.time() - batch_start
                    wait = max(0.0, 60.0 - elapsed)
                    if wait > 0:
                        logger.info(
                            f"Batch {batch_idx + 1} took {elapsed:.1f}s; "
                            f"waiting {wait:.1f}s before next batch (rate limit)"
                        )
                        time.sleep(wait)

            iteration += 1
            if max_iterations and iteration >= max_iterations:
                logger.info(f"Reached maximum iterations ({max_iterations})")
                break

            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        logger.info("Polling stopped by user (Ctrl+C)")
    finally:
        elapsed = time.time() - start_time
        logger.info(
            f"Polling completed: {iteration} iterations in {elapsed:.1f} seconds"
        )


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Poll CPE signal metrics at regular intervals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s CPE123456 --interval 60 --iterations 10
      Poll specific CPE every 1 minute for 10 iterations

  %(prog)s --file cpe-device-sn.txt --interval 30
      Poll CPE devices listed in file every 30 seconds

  %(prog)s --interval 30
      Poll all available CPE devices every 30 seconds

  %(prog)s --devices 5 --interval 60
      Poll first 5 CPE devices every minute
        """,
    )
    add_device_args(parser)
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    level = logging.DEBUG if args.verbose else logging.INFO
    for name in ("baicells_client", "get_metrics", __name__):
        logging.getLogger(name).setLevel(level)

    # Initialize client
    try:
        client = BaiCellsClient(
            base_url=args.url,
            username=args.username,
            password=args.password,
        )
    except ValueError as e:
        logger.error(
            "%s\n\nMake sure you have a .env file with credentials or pass them via CLI.",
            e,
        )
        sys.exit(1)

    # Determine which CPE devices to monitor
    try:
        serial_numbers = resolve_serial_numbers(args, client)
    except Exception as e:
        logger.error(f"Error querying CPE devices: {e}")
        sys.exit(1)

    # Start polling
    try:
        poll_metrics(
            client=client,
            serial_numbers=serial_numbers,
            interval_seconds=args.interval or 60,
            max_iterations=args.iterations,
        )
    except Exception as e:
        logger.error(f"Polling error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
