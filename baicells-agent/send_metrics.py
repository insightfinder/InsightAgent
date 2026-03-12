#!/usr/bin/env python3
"""
Send BaiCells CPE signal metrics to InsightFinder.

This script:
1. Reads CPE device serial numbers from cpe-device-sn.txt (by default)
2. Polls signal quality metrics at a configurable interval
3. Transforms data to InsightFinder format
4. Sends data to InsightFinder
"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

from baicells_client import BaiCellsClient
from get_metrics import add_device_args, resolve_serial_numbers
from insightfinder import Config, InsightFinder

logger = logging.getLogger(__name__)


def transform_to_insightfinder(
    serial_number: str,
    cpe_info: dict[str, Any],
    timestamp_ms: int,
) -> dict[str, Any]:
    """Transform CPE signal metrics into InsightFinder v2 instance data format.

    Args:
        serial_number: CPE device serial number (used as the instance name)
        cpe_info: Raw CPE info dict from BaiCellsClient.get_cpe_info()
        timestamp_ms: Unix timestamp in milliseconds for this data point

    Returns:
        Per-device data structure suitable for merging into an InsightFinder payload
    """
    metrics: list[dict[str, Any]] = []

    metric_fields = {
        "rsrp0": "rsrp0",
        "rsrp1": "rsrp1",
        "cpeSinr": "sinr",
        "cinr0": "cinr0",
        "cinr1": "cinr1",
        "nrRsrp": "nr_rsrp",
        "nrRsrq": "nr_rsrq",
        "nrSinr": "nr_sinr",
        "nrCinr": "nr_cinr",
    }
    # RSRP values are in dBm and always negative; use abs() to make them positive.
    rsrp_fields = {"rsrp0", "rsrp1", "nrRsrp"}
    for src_key, metric_name in metric_fields.items():
        value = cpe_info.get(src_key)
        if value is not None and str(value).strip() != "":
            try:
                v = float(value)
                if src_key in rsrp_fields:
                    v = abs(v)
                metrics.append({"m": metric_name, "v": v})
            except (ValueError, TypeError):
                logger.debug(f"Skipping non-numeric value for {src_key}: {value!r}")

    ts_str = str(timestamp_ms)
    return {
        serial_number: {
            "in": serial_number,
            "dit": {
                ts_str: {
                    "t": timestamp_ms,
                    "metricDataPointSet": metrics,
                }
            },
        }
    }


def poll_and_send(
    client: BaiCellsClient,
    if_client: InsightFinder,
    serial_numbers: list[str],
    interval_seconds: int = 60,
    max_iterations: int | None = None,
    verbose: bool = False,
) -> None:
    """Poll CPE signal metrics at regular intervals and send them to InsightFinder.

    Args:
        client: BaiCellsClient instance
        if_client: InsightFinder client instance
        serial_numbers: List of CPE serial numbers to monitor
        interval_seconds: Polling interval in seconds (default: 60)
        max_iterations: Maximum number of polls (None = infinite)
    """
    BATCH_SIZE = 20
    device_count = len(serial_numbers)
    batches = [
        serial_numbers[i : i + BATCH_SIZE] for i in range(0, device_count, BATCH_SIZE)
    ]
    logger.info(
        f"Starting metrics polling for {device_count} device(s) in {len(batches)} batch(es) "
        f"@ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    logger.info(f"Interval: {interval_seconds}s")
    if max_iterations:
        logger.info(f"Max iterations: {max_iterations}")
    start_time = time.time()
    iteration = 0

    try:
        while True:
            iteration_start = time.time()
            ts_human_iter = datetime.fromtimestamp(
                iteration_start, timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S UTC")
            logger.info(
                f"Iteration {iteration + 1}: collecting metrics at {ts_human_iter}"
            )

            iteration_timestamp_ms = int(iteration_start * 1000)
            for batch_idx, batch in enumerate(batches):
                batch_start = time.time()
                batch_payload: dict[str, Any] = {}
                batch_offset = batch_idx * BATCH_SIZE

                for idx, serial_number in enumerate(batch, batch_offset + 1):
                    logger.info(
                        f"[{idx}/{device_count}] Fetching metrics for {serial_number}"
                    )
                    try:
                        cpe_info = client.get_cpe_info(serial_number)
                        device_data = transform_to_insightfinder(
                            serial_number, cpe_info, iteration_timestamp_ms
                        )
                        batch_payload.update(device_data)

                        if verbose:
                            rsrp0 = cpe_info.get("rsrp0", "N/A")
                            rsrp1 = cpe_info.get("rsrp1", "N/A")
                            sinr = cpe_info.get("cpeSinr", "N/A")
                            cinr0 = cpe_info.get("cinr0", "N/A")
                            cinr1 = cpe_info.get("cinr1", "N/A")
                            logger.info(
                                f"  ✓ {serial_number:<22} "
                                f"rsrp0={str(rsrp0):<8} rsrp1={str(rsrp1):<8} "
                                f"sinr={str(sinr):<8} cinr0={str(cinr0):<8} cinr1={str(cinr1)}"
                            )
                            nr_rsrp = cpe_info.get("nrRsrp")
                            nr_rsrq = cpe_info.get("nrRsrq")
                            nr_sinr = cpe_info.get("nrSinr")
                            nr_cinr = cpe_info.get("nrCinr")
                            if any(
                                v is not None and str(v).strip() != ""
                                for v in [nr_rsrp, nr_rsrq, nr_sinr, nr_cinr]
                            ):
                                logger.info(
                                    f"    └─ 5G NR: rsrp={nr_rsrp} rsrq={nr_rsrq} sinr={nr_sinr} cinr={nr_cinr}"
                                )
                    except Exception as e:
                        logger.warning(f"  ✗ {serial_number:<22} ERROR: {e}")

                if batch_payload:
                    try:
                        logger.debug(f"Payload:\n{json.dumps(batch_payload, indent=2)}")
                        if_client.send_metric(batch_payload)
                        logger.info(
                            f"Sent {len(batch_payload)} device(s) to InsightFinder project '{if_client.config.project_name}'"
                        )
                    except Exception as e:
                        logger.error(f"Send failed: {e}")

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

            elapsed = time.time() - iteration_start
            wait = max(0.0, interval_seconds - elapsed)
            if wait > 0:
                logger.info(
                    f"Iteration {iteration} took {elapsed:.1f}s; "
                    f"sleeping {wait:.1f}s before next iteration"
                )
                time.sleep(wait)

    except KeyboardInterrupt:
        logger.info("Polling stopped by user (Ctrl+C)")
    finally:
        elapsed = time.time() - start_time
        logger.info(
            f"Polling completed: {iteration} iterations in {elapsed:.1f} seconds"
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Poll CPE signal metrics and send them to InsightFinder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s
      Poll devices from cpe-device-sn.txt every 60 seconds

  %(prog)s CPE123456 --interval 30
      Poll a specific CPE every 30 seconds

  %(prog)s --file devices.txt --iterations 10
      Poll devices from a custom file for 10 iterations

  %(prog)s --devices 5
      Poll first 5 online CPE devices (auto-discovered)
        """,
    )
    add_device_args(parser)

    if_group = parser.add_argument_group("InsightFinder options")
    if_group.add_argument(
        "--if-url", default=None, help="InsightFinder URL (overrides .env)"
    )
    if_group.add_argument(
        "--if-user", default=None, help="InsightFinder username (overrides .env)"
    )
    if_group.add_argument(
        "--if-key", default=None, help="InsightFinder license key (overrides .env)"
    )
    if_group.add_argument(
        "--if-project",
        default=None,
        help="InsightFinder project name (overrides .env)",
    )

    parser.add_argument(
        "--log-file",
        default=None,
        metavar="FILE",
        help="Write log messages to this file instead of stdout (e.g. output.log)",
    )
    parser.add_argument(
        "--log-max-bytes",
        type=int,
        default=10 * 1024 * 1024,
        metavar="BYTES",
        help="Max log file size before rotation (default: 10 MiB; ignored without --log-file)",
    )
    parser.add_argument(
        "--log-backup-count",
        type=int,
        default=5,
        metavar="N",
        help="Number of rotated log files to keep (default: 5; ignored without --log-file)",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    load_dotenv()

    level = logging.DEBUG if args.verbose else logging.INFO

    if args.log_file:
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            args.log_file,
            maxBytes=args.log_max_bytes,
            backupCount=args.log_backup_count,
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    handler.setLevel(level)
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.addHandler(handler)

    for name in (
        "baicells_client",
        "insightfinder",
        "send_metrics",
        "get_metrics",
        __name__,
    ):
        logging.getLogger(name).setLevel(level)

    # Build InsightFinder config from .env with CLI overrides
    if_url = args.if_url or os.getenv("INSIGHTFINDER_BASE_URL")
    if_user = args.if_user or os.getenv("INSIGHTFINDER_USER_NAME")
    if_key = args.if_key or os.getenv("INSIGHTFINDER_LICENSE_KEY")
    if_project = args.if_project or os.getenv("INSIGHTFINDER_PROJECT_NAME")
    if_system = os.getenv("INSIGHTFINDER_SYSTEM_NAME")
    sampling_interval_min = int(os.getenv("INSIGHTFINDER_SAMPLING_INTERVAL", "1"))

    missing = [
        name
        for name, val in [
            ("INSIGHTFINDER_BASE_URL / --if-url", if_url),
            ("INSIGHTFINDER_USER_NAME / --if-user", if_user),
            ("INSIGHTFINDER_LICENSE_KEY / --if-key", if_key),
            ("INSIGHTFINDER_PROJECT_NAME / --if-project", if_project),
        ]
        if not val
    ]
    if missing:
        logger.error(
            "Missing InsightFinder credentials:\n  %s\n\nSet them in .env or pass via CLI flags.",
            "\n  ".join(missing),
        )
        return 1

    if_config = Config(
        url=if_url,
        user_name=if_user,
        license_key=if_key,
        project_name=if_project,
        agent_type="custom",
        system_name=if_system,
        data_type="Metric",
        insight_agent_type="Custom",
        samplingInterval=sampling_interval_min * 60,
        create_project=True,
    )

    # Initialize BaiCells client
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
        return 1

    # Resolve device list
    try:
        serial_numbers = resolve_serial_numbers(args, client)
    except Exception as e:
        logger.error(f"Error querying CPE devices: {e}")
        return 1

    # Start polling and sending
    interval_seconds = args.interval or (sampling_interval_min * 60)
    with InsightFinder(if_config) as if_client:
        try:
            poll_and_send(
                client=client,
                if_client=if_client,
                serial_numbers=serial_numbers,
                interval_seconds=interval_seconds,
                max_iterations=args.iterations,
                verbose=args.verbose,
            )
        except Exception as e:
            logger.error(f"Polling error: {e}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
