#!/usr/bin/env python3
"""
Scheduler for rawlogs_agent.py: re-invokes it every config.yaml
collection.interval_seconds. A system crontab or k8s CronJob works just as
well; this is for deployments that want scheduling with nothing but Python.
"""
import argparse
import logging
import os
import subprocess
import sys

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler

logger = logging.getLogger('insightfinder_rawlogs.cron')

HERE = os.path.dirname(os.path.abspath(__file__))


def get_python_cmd() -> str:
    venv_python = os.path.join(HERE, 'venv', 'bin', 'python3')
    if os.path.exists(venv_python):
        return venv_python
    return sys.executable or 'python3'


def get_cron_params(interval_seconds: int) -> dict:
    """Convert a plain interval into APScheduler cron trigger kwargs, picking
    the coarsest unit that fits so the trigger reads naturally."""
    unit = 'second'
    interval = interval_seconds
    if interval % 60 == 0:
        interval //= 60
        unit = 'minute'
        if interval % 60 == 0:
            interval //= 60
            unit = 'hour'
            if interval % 24 == 0:
                interval //= 24
                unit = 'day'
    return {unit: f'*/{interval}'}


def run_job(python_cmd: str, config_path: str, log_level_flag: list):
    cmd = [python_cmd, os.path.join(HERE, 'rawlogs_agent.py'), '-c', config_path,
          *log_level_flag]
    logger.info("Running: %s", ' '.join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        logger.warning("rawlogs_agent.py exited with code %d", result.returncode)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-c', '--config', default=os.path.join(HERE, 'config.yaml'),
                       help='Path to config.yaml (default: ./config.yaml)')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-q', '--quiet', action='store_true')
    return parser.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)-8s %(name)s | %(message)s')
    args = parse_args(argv)

    if not os.path.exists(args.config):
        logger.error("Config file not found: %s", args.config)
        return 1

    with open(args.config) as fp:
        raw_cfg = yaml.safe_load(fp) or {}

    collection = raw_cfg.get('collection') or {}
    if collection.get('replay'):
        logger.error("collection.replay is set in %s - that is a one-shot backfill; "
                    "run rawlogs_agent.py directly instead of scheduling it via cron.py.",
                    args.config)
        return 1

    interval_seconds = int(collection.get('interval_seconds', 60))
    log_level_flag = ['-v'] if args.verbose else (['-q'] if args.quiet else [])
    python_cmd = get_python_cmd()
    cron_params = get_cron_params(interval_seconds)

    logger.info("Scheduling rawlogs_agent.py every %ds (%s) using %s",
               interval_seconds, cron_params, python_cmd)

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_job, 'cron', args=(python_cmd, args.config, log_level_flag),
        **cron_params, name=os.path.basename(args.config), coalesce=True,
        max_instances=1, misfire_grace_time=interval_seconds,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())
