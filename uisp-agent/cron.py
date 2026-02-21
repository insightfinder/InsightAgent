#!/usr/bin/env python3
"""
Automated scheduler for UISP metrics collection.

This script runs send_metrics.py at intervals defined by INSIGHTFINDER_SAMPLING_INTERVAL
in the .env file. It fetches only the latest data point per device using an overlapping
window strategy to prevent data gaps.

Usage:
    python cron.py              # Start scheduler (runs in foreground)
    python cron.py -v           # Start scheduler with verbose logging (shows payloads)
    python cron.py -n 10        # Start scheduler and limit to 10 devices
    python cron.py -v -n 10     # Start scheduler with verbose logging and limit to 10 devices

Configuration:
    Reads INSIGHTFINDER_SAMPLING_INTERVAL from .env file (in minutes)
    - If interval = 1 minute, runs every 1 minute and fetches last 2 minutes
    - If interval = 5 minutes, runs every 5 minutes and fetches last 10 minutes

Output:
    All output is sent to stdout
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler


def run_job(python_cmd, script_path, script_args, logger):
    """Execute send_metrics.py via subprocess.

    Args:
        python_cmd: Path to Python executable
        script_path: Path to send_metrics.py
        script_args: Command-line arguments for send_metrics.py
        logger: Logger instance for output
    """
    start_time = time.time()
    command = [python_cmd, script_path] + script_args.split()
    try:
        logger.info("Starting job execution...")
        result = subprocess.run(
            command,
            timeout=300,  # 5 minute timeout
            capture_output=True,
            text=True,
        )

        # Print subprocess output directly (already formatted by subprocess)
        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)

        elapsed = time.time() - start_time
        logger.info(f"Job completed in {elapsed:.2f} seconds")
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        logger.warning(f"Job execution timed out after {elapsed:.2f} seconds")
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Job execution failed after {elapsed:.2f} seconds: {e}")


def get_cron_params(interval_seconds):
    """Convert interval in seconds to cron parameters.

    Args:
        interval_seconds: Interval in seconds

    Returns:
        Dictionary with cron parameters (e.g., {'minute': '*/5'})
    """
    if interval_seconds >= 3600:  # 60 minutes
        interval = interval_seconds // 3600
        unit = "hour"
    elif interval_seconds >= 60:
        interval = interval_seconds // 60
        unit = "minute"
    else:
        interval = interval_seconds
        unit = "second"

    return {unit: f"*/{interval}"}


def format_period(seconds):
    """Format seconds into period string for send_metrics.py.

    Args:
        seconds: Number of seconds

    Returns:
        Period string (e.g., '2m', '10m', '2h')
    """
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    else:
        return f"{seconds // 3600}h"


def main():
    """Main scheduler function."""

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Automated scheduler for UISP metrics collection"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging (shows payloads in send_metrics.py)",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        help="Limit the number of devices to process",
    )
    args = parser.parse_args()

    # Load environment variables from .env file
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        print(f"ERROR: .env file not found at {env_path}", file=sys.stderr)
        print(
            "Please create a .env file with INSIGHTFINDER_SAMPLING_INTERVAL",
            file=sys.stderr,
        )
        sys.exit(1)

    load_dotenv(env_path)

    # Get sampling interval from environment (in minutes)
    sampling_interval_str = os.getenv("INSIGHTFINDER_SAMPLING_INTERVAL")
    if not sampling_interval_str:
        print(
            "ERROR: INSIGHTFINDER_SAMPLING_INTERVAL not found in .env file",
            file=sys.stderr,
        )
        sys.exit(1)

    # Get device limit from command line argument
    device_limit = args.limit

    # Validate and convert to integer (minutes to seconds)
    try:
        sampling_interval_minutes = int(sampling_interval_str)
        if sampling_interval_minutes <= 0:
            raise ValueError("Interval must be positive")
        sampling_interval = sampling_interval_minutes * 60  # Convert to seconds
    except ValueError as e:
        print(
            f"ERROR: Invalid INSIGHTFINDER_SAMPLING_INTERVAL '{sampling_interval_str}': {e}",
            file=sys.stderr,
        )
        print("Must be a positive integer (minutes)", file=sys.stderr)
        sys.exit(1)

    # Calculate fetch period (2x interval for overlapping windows to prevent gaps)
    fetch_period_seconds = sampling_interval * 2
    fetch_period = format_period(fetch_period_seconds)

    # Build cron parameters
    cron_params = get_cron_params(sampling_interval)

    # Determine Python executable
    venv_python = os.path.join(os.path.dirname(__file__), ".venv", "bin", "python3")
    if os.path.exists(venv_python):
        python_cmd = venv_python
        print(f"Using virtual environment Python: {python_cmd}")
    else:
        python_cmd = "python3"
        print(f"No virtual environment found, using system Python: {python_cmd}")

    # Get script path
    script_path = os.path.join(os.path.dirname(__file__), "send_metrics.py")
    if not os.path.exists(script_path):
        print(f"ERROR: send_metrics.py not found at {script_path}", file=sys.stderr)
        sys.exit(1)

    # Build script arguments
    script_args = f"--num-points 1 --period {fetch_period}"
    if device_limit is not None:
        script_args += f" -n {device_limit}"
    if args.verbose:
        script_args += " -v"

    # Set up console handler for stdout output
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )

    # Configure logger
    logger = logging.getLogger("uisp_cron")
    logger.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    # Print configuration
    print("=" * 60)
    print("UISP Metrics Scheduler Configuration")
    print("=" * 60)
    print(
        f"Sampling Interval: {sampling_interval_minutes} minutes ({sampling_interval} seconds)"
    )
    print(f"Fetch Period: {fetch_period} (2x interval)")
    print(f"Device Limit: {device_limit if device_limit else 'All devices'}")
    print(f"Verbose Mode: {'Enabled' if args.verbose else 'Disabled'}")
    print(f"Schedule: {cron_params}")
    print("Max Instances: 1 (prevents overlap)")
    print("Coalesce: True (combines missed runs)")
    print(f"Misfire Grace: {sampling_interval} seconds")
    print("Job Timeout: 300 seconds")
    print(f"Python: {python_cmd}")
    print(f"Script: {script_path}")
    print(f"Arguments: {script_args}")
    print("=" * 60)
    print("")
    print(
        f"Scheduler will run send_metrics.py every {sampling_interval_minutes} minutes"
    )
    print(f"Each run fetches the latest data point from a {fetch_period} window")
    print("")
    print("Press Ctrl+C to stop the scheduler")
    print("=" * 60)
    print("")

    # Run job immediately on startup
    print("Running initial job execution...")
    run_job(python_cmd, script_path, script_args, logger)
    print("")

    # Create scheduler
    scheduler = BlockingScheduler()

    # Add job with max_instances to prevent overlap
    scheduler.add_job(
        run_job,
        "cron",
        args=(python_cmd, script_path, script_args, logger),
        max_instances=1,  # Prevent job overlap
        coalesce=True,  # Combine missed runs into single execution
        misfire_grace_time=sampling_interval,  # Allow job to start up to 1 interval late
        **cron_params,
    )

    # Start scheduler
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nShutting down scheduler...")
        scheduler.shutdown(wait=False)
        print("Scheduler stopped")


if __name__ == "__main__":
    main()
