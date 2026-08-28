#!/usr/bin/env python3
"""AccessParks device metadata reconciliation agent.

For every device reported by a vendor controller, looks it up in Jira Assets
and in Zabbix and ships one log record per device to InsightFinder, so gaps
between the three sources become queryable there.

Usage:
    python main.py                          # all controllers, resolve, send
    python main.py --controllers unifi       # only the named controller(s)
    python main.py --exclude-controllers baicells  # all controllers except these
    python main.py --dry-run                 # resolve + print table, send nothing
    python main.py --table                   # print table AND send
    python main.py --json                    # print raw log records instead of a table
    python main.py --limit 10                # cap devices per controller
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
import urllib3

# Vendor controllers connect with verify=False (self-signed certs on several of
# these instances) — silence the resulting per-request InsecureRequestWarning
# instead of letting it flood the log for every device fetch.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import load_config
from controllers import CONTROLLER_FACTORIES
from controllers import build_controllers
from insightfinder import Config as IFConfig
from insightfinder import InsightFinder
from jira_assets import JiraAssetClient
from models import ReconciledDevice
from reconcile import build_instance_tags
from reconcile import build_log_data
from reconcile import reconcile_device
from zabbix import build_index as build_zabbix_index

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

# Each device does up to 3 sequential Jira Asset Registry lookups plus a live
# Zabbix tag RPC — at fleet scale (thousands of devices) that's minutes of
# per-device network latency. Bounded concurrency here matches the pattern
# already used for NetExperience/Baicells per-device network loops.
RECONCILE_CONCURRENCY = 20


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--controllers",
        help="Comma-separated controller names to run (default: all registered). "
        f"Available: {', '.join(CONTROLLER_FACTORIES)}",
    )
    p.add_argument(
        "--exclude-controllers",
        help="Comma-separated controller names to skip (default: none). "
        "Mutually exclusive with --controllers.",
    )
    p.add_argument("--table", action="store_true", help="Print a human-readable per-device table")
    p.add_argument("--dry-run", action="store_true", help="Resolve and print, send nothing (implies --table)")
    p.add_argument("--json", action="store_true", dest="as_json", help="Print raw log records as JSON instead of a table")
    p.add_argument("--limit", type=int, default=None, help="Cap the number of devices per controller")
    return p.parse_args()


def print_table(rows: list[ReconciledDevice]) -> None:
    headers = ["CONTROLLER", "DEVICE", "CTRL IP", "CTRL MAC", "JIRA KEY", "JIRA IP", "JIRA MAC", "ZBX ID", "STATUS"]
    table: list[list[str]] = []
    for r in rows:
        d = r.controller_device
        jira = r.jira
        zabbix = r.zabbix

        status_parts = []
        if r.jira_error:
            status_parts.append("jira-error")
        elif jira is None:
            status_parts.append("no-jira")
        if r.zabbix_error:
            status_parts.append("zabbix-error")
        elif zabbix is None:
            status_parts.append("no-zabbix")

        jira_ip = jira.ip if jira else "-"
        jira_mac = jira.mac if jira else "-"
        if jira and jira.ip and d.ip and jira.ip != d.ip:
            jira_ip += " ≠"
            status_parts.append("ip≠")
        if jira and jira.mac and d.mac and jira.mac.lower() != d.mac.lower():
            jira_mac += " ≠"
            status_parts.append("mac≠")

        table.append(
            [
                d.controller,
                d.name,
                d.ip or "-",
                d.mac or "-",
                jira.object_key if jira else "-",
                jira_ip,
                jira_mac,
                zabbix.hostid if zabbix else "-",
                ", ".join(status_parts) or "ok",
            ]
        )

    widths = [max(len(h), *(len(row[i]) for row in table)) if table else len(h) for i, h in enumerate(headers)]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    for row in table:
        print("  ".join(c.ljust(w) for c, w in zip(row, widths)))


def build_summary(rows: list[ReconciledDevice], jira_errors: int, zabbix_errors: int = 0) -> str:
    total = len(rows)
    jira_matched = sum(1 for r in rows if r.jira)
    jira_missing = sum(1 for r in rows if r.jira is None and not r.jira_error)
    zabbix_matched = sum(1 for r in rows if r.zabbix)
    zabbix_missing = sum(1 for r in rows if r.zabbix is None and not r.zabbix_error)
    ip_mismatch = sum(1 for r in rows if r.jira and r.jira.ip and r.controller_device.ip and r.jira.ip != r.controller_device.ip)
    mac_mismatch = sum(
        1
        for r in rows
        if r.jira and r.jira.mac and r.controller_device.mac and r.jira.mac.lower() != r.controller_device.mac.lower()
    )
    extra = f" | jira lookup errors (excluded): {jira_errors}" if jira_errors else ""
    extra += f" | zabbix lookup errors (unresolved): {zabbix_errors}" if zabbix_errors else ""
    return (
        f"{total} devices | jira: {jira_matched} matched, {jira_missing} missing"
        f" | zabbix: {zabbix_matched} matched, {zabbix_missing} missing"
        f" | ip mismatch: {ip_mismatch} | mac mismatch: {mac_mismatch}{extra}"
    )


def main() -> int:
    args = parse_args()
    cfg = load_config()

    if not (cfg.zabbix_url and cfg.zabbix_user and cfg.zabbix_password):
        logger.error("ZABBIX_URL/ZABBIX_USER/ZABBIX_PASSWORD not set in .env — aborting, nothing sent.")
        return 1

    if args.controllers and args.exclude_controllers:
        logger.error("--controllers and --exclude-controllers are mutually exclusive.")
        return 1

    # dict.fromkeys dedupes while preserving order — a repeated name would otherwise
    # build multiple instances of the same controller and run them concurrently,
    # which for Baicells would race on its shared IP-enrichment cache file.
    controller_names = (
        list(dict.fromkeys(c.strip() for c in args.controllers.split(","))) if args.controllers else None
    )
    if args.exclude_controllers:
        excluded = {c.strip() for c in args.exclude_controllers.split(",")}
        unknown = excluded - set(CONTROLLER_FACTORIES)
        if unknown:
            logger.error("Unknown controller(s) in --exclude-controllers: %s", ", ".join(sorted(unknown)))
            return 1
        controller_names = [name for name in CONTROLLER_FACTORIES if name not in excluded]

    controllers = build_controllers(cfg, only=controller_names)
    if not controllers:
        logger.error("No controllers available to run (check .env credentials).")
        return 1

    def collect(controller):
        logger.info("Collecting devices from %r...", controller.name)
        try:
            devices = controller.list_devices()
        except Exception as e:  # noqa: BLE001 - a vendor API failure must not crash the whole run
            logger.error("Controller %r failed: %s", controller.name, e)
            return controller.name, []
        if not devices:
            logger.warning("Controller %r returned no devices — skipping (API may be down)", controller.name)
            return controller.name, []
        if args.limit is not None:
            devices = devices[: args.limit]
        return controller.name, devices

    all_devices = []
    with ThreadPoolExecutor(max_workers=len(controllers)) as executor:
        results = list(executor.map(collect, controllers))
    logger.info(
        "Per-controller device counts: %s",
        ", ".join(f"{name}={len(devices)}" for name, devices in results),
    )
    for _, devices in results:
        all_devices.extend(devices)

    if not all_devices:
        logger.error("No devices collected from any controller — aborting, nothing sent.")
        return 1

    jira_client = JiraAssetClient(base_url=cfg.jira_base, api_key=cfg.jira_api_key)
    if not jira_client.health_ok():
        logger.error("Jira Asset Registry health check failed at %s — aborting, nothing sent.", cfg.jira_base)
        return 1

    try:
        zabbix_index = build_zabbix_index(
            cfg.zabbix_url, cfg.zabbix_user, cfg.zabbix_password, pool_size=RECONCILE_CONCURRENCY
        )
    except RuntimeError as e:
        logger.error(
            "%s (is the tunnel up? see scripts/zabbix-tunnel.sh) — aborting, nothing sent.", e
        )
        return 1

    total = len(all_devices)
    logger.info("Reconciling %d device(s) against Jira Assets and Zabbix...", total)
    reconciled: list[ReconciledDevice] = []
    jira_errors = 0
    zabbix_errors = 0
    completed = 0
    with ThreadPoolExecutor(max_workers=RECONCILE_CONCURRENCY) as executor:
        for r in executor.map(lambda d: reconcile_device(d, jira_client, zabbix_index), all_devices):
            completed += 1
            if completed % 250 == 0 or completed == total:
                logger.info("Reconciled %d/%d device(s)", completed, total)
            if r.jira_error:
                jira_errors += 1
                logger.warning("Jira lookup error for %r — excluded from batch", r.controller_device.name)
                continue
            if r.zabbix_error:
                zabbix_errors += 1
                logger.warning(
                    "Zabbix lookup error for %r — reported as unresolved, not missing", r.controller_device.name
                )
            reconciled.append(r)

    summary = build_summary(reconciled, jira_errors, zabbix_errors)
    if args.as_json:
        # Keep stdout as pure, pipeable JSON — the summary goes to the log instead.
        print(json.dumps([build_log_data(r) for r in reconciled], indent=2))
        logger.info(summary)
    else:
        if args.table or args.dry_run:
            print_table(reconciled)
        print(f"\n{summary}")

    if args.dry_run:
        logger.info("Dry run — nothing sent to InsightFinder.")
        return 0

    ts = int(time.time() * 1000)
    tags = build_instance_tags([r.controller_device for r in reconciled])
    renamed = 0
    logs = []
    for r, tag in zip(reconciled, tags):
        if tag != r.controller_device.name:
            renamed += 1
        log_entry = {
            "timestamp": ts,
            "tag": tag,
            "data": json.dumps(build_log_data(r)),
        }
        if cfg.if_set_component:
            log_entry["componentName"] = r.controller_device.controller
        logs.append(log_entry)
    if renamed:
        logger.info("Sanitized/disambiguated %d instance name(s) for InsightFinder", renamed)

    if_config = IFConfig(
        url=cfg.if_url,
        user_name=cfg.if_user_name,
        license_key=cfg.if_license_key,
        project_name=cfg.if_project_name,
        agent_type="LogStreaming",
        data_type="Log",
        insight_agent_type="Custom",
        instance_type="PrivateCloud",
        system_name=cfg.if_system_name,
        sampling_interval=cfg.if_sampling_interval * 3600,  # config is in hours; the API's samplingInterval is in seconds
        create_project=True,
    )
    try:
        with InsightFinder(if_config) as client:
            client.send_log(logs)
    except requests.exceptions.RequestException as e:
        logger.error("Failed to send log data to InsightFinder: %s", e)
        return 1

    logger.info("Sent %d log record(s) to InsightFinder project %r", len(logs), cfg.if_project_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
