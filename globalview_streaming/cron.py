#!/usr/bin/env python
"""
Scheduler for the GlobalView streaming agent.

Globs conf.d/*.ini and schedules send_gv_data.py once per config file at that
config's [insightfinder] run_interval (each config -c <ini>). This is the
container entrypoint; it keeps the agent running on a fixed cadence.
"""
import configparser
import glob
import logging
import os
import subprocess
import sys
from optparse import OptionParser

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_SUBMITTED
from apscheduler.schedulers.blocking import BlockingScheduler

SCRIPT_NAME = 'send_gv_data.py'

# StreamHandler flushes on every record, so logs stream to `kubectl logs`
# without relying on PYTHONUNBUFFERED.
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format='%(asctime)s [cron] %(levelname)-7s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger('cron')


def run_job(python_cmp, file_agent, config_ini, config_vars):
    name = os.path.basename(config_ini)
    logger.info('Running agent for %s', name)

    cmd = [python_cmp, file_agent, '-c', config_ini,
           '--timeout', str(config_vars['worker_timeout'])]
    if config_vars['log_level']:
        cmd.append(config_vars['log_level'])

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True)
    except Exception as e:
        logger.exception('Failed to launch agent for %s: %s', name, e)
        return

    # echo the agent's own output (stdout+stderr) so its logs/errors show up
    # in the container logs, preserving its native formatting.
    output = (proc.stdout or '').rstrip()
    if output:
        print('----- agent output ({}) -----'.format(name), flush=True)
        print(output, flush=True)
        print('----- end agent output ({}) -----'.format(name), flush=True)

    if proc.returncode == 0:
        logger.info('Agent for %s finished (exit 0)', name)
    else:
        logger.error('Agent for %s FAILED (exit %s)', name, proc.returncode)


def get_cron_params(interval_seconds, offset):
    """ convert an interval in seconds into APScheduler cron kwargs """
    if interval_seconds < 60:
        return {'second': '*/{}'.format(max(1, interval_seconds))}
    minutes = interval_seconds // 60
    if minutes < 60:
        return {'minute': '*/{}'.format(minutes), 'second': str(offset)}
    hours = minutes // 60
    if hours < 24:
        return {'hour': '*/{}'.format(hours), 'minute': '0', 'second': str(offset)}
    days = hours // 24
    return {'day': '*/{}'.format(days), 'hour': '0', 'minute': '0', 'second': str(offset)}


def parse_interval(value, default_seconds):
    """ '20' -> minutes, '30s' -> seconds; empty -> default """
    value = (value or '').strip()
    if not value:
        return default_seconds
    if value.endswith('s'):
        return int(value[:-1])
    return int(value) * 60


def get_cli_config_vars():
    parser = OptionParser(usage='Usage: %prog [options]')
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-g', '--group', action='store', dest='group_size', default=3,
                      help='Number of config files per stagger group')
    parser.add_option('-o', '--offset', action='store', dest='offset', default=3,
                      help='Stagger offset in seconds')
    (options, args) = parser.parse_args()
    config_vars = {
        'group': int(options.group_size),
        'offset': int(options.offset),
        'log_level': '',
    }
    if options.verbose:
        config_vars['log_level'] = '-v'
    elif options.quiet:
        config_vars['log_level'] = '-q'
    return config_vars


def log_scheduler_event(event):
    job_id = getattr(event, 'job_id', '?')
    if event.code == EVENT_JOB_SUBMITTED:
        logger.info('Job fired: %s', job_id)
    elif event.code == EVENT_JOB_EXECUTED:
        logger.info('Job finished: %s', job_id)
    elif event.code == EVENT_JOB_ERROR:
        logger.error('Job errored: %s -> %s', job_id, event.exception)


def main():
    scheduler = BlockingScheduler()
    scheduler.add_listener(log_scheduler_event,
                           EVENT_JOB_SUBMITTED | EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    here = os.path.abspath(os.path.dirname(__file__))

    logger.info('GlobalView streaming cron starting (dir=%s)', here)

    conf_files = sorted(glob.glob(os.path.join(here, 'conf.d', '*.ini')))
    if not conf_files:
        logger.error('No conf.d/*.ini file found. Exiting...')
        return False
    logger.info('Found %d config file(s): %s', len(conf_files),
                ', '.join(os.path.basename(f) for f in conf_files))

    config_vars = get_cli_config_vars()

    # python interpreter: local venv if present, else python3
    python_cmp = os.path.join(here, 'venv', 'bin', 'python3')
    if not os.path.exists(python_cmp):
        python_cmp = 'python3'

    file_agent = os.path.join(here, SCRIPT_NAME)
    if not os.path.exists(file_agent):
        logger.error('No %s found. Exiting...', SCRIPT_NAME)
        return False

    counter = 1
    offset = 0
    scheduled = 0
    for config_ini in conf_files:
        try:
            parser = configparser.ConfigParser()
            with open(config_ini) as fp:
                parser.read_file(fp)
            run_interval = parse_interval(parser.get('insightfinder', 'run_interval',
                                                      fallback=''), 60)
            worker_timeout = parse_interval(parser.get('insightfinder', 'worker_timeout',
                                                        fallback=''), run_interval)
        except Exception as e:
            logger.warning('Skipping %s: %s', config_ini, e)
            counter += 1
            continue

        per_job = dict(config_vars)
        per_job['worker_timeout'] = worker_timeout

        if counter % config_vars['group'] == 0:
            offset += config_vars['offset']
        cron_params = get_cron_params(run_interval, offset)

        name = os.path.basename(config_ini)
        scheduler.add_job(
            run_job, 'cron', (python_cmp, file_agent, config_ini, per_job),
            **cron_params, id=name, name=name, coalesce=True,
            misfire_grace_time=run_interval)
        logger.info('Scheduled %s: every %ds (cron=%s)', name, run_interval, cron_params)
        scheduled += 1
        counter += 1

    if scheduled == 0:
        logger.error('No configs scheduled. Exiting...')
        return False

    logger.info('Scheduler started with %d job(s); waiting for next run tick...', scheduled)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info('Scheduler shutting down.')
        scheduler.shutdown(wait=False)


if __name__ == '__main__':
    main()
