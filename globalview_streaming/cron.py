#!/usr/bin/env python
"""
Scheduler for the GlobalView streaming agent.

Globs conf.d/*.ini and schedules send_gv_data.py once per config file at that
config's [insightfinder] run_interval (each config -c <ini>). This is the
container entrypoint; it keeps the agent running on a fixed cadence.
"""
import configparser
import glob
import os
import subprocess
from optparse import OptionParser

from apscheduler.schedulers.blocking import BlockingScheduler

SCRIPT_NAME = 'send_gv_data.py'


def run_job(python_cmp, file_agent, config_ini, config_vars):
    print('Start {}'.format(config_ini))
    subprocess.run(
        '{py} {agent} {lvl} -c {cfg} --timeout={timeout} 2>&1'.format(
            py=python_cmp, agent=file_agent, lvl=config_vars['log_level'],
            cfg=config_ini, timeout=config_vars['worker_timeout']),
        shell=True)


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


def main():
    scheduler = BlockingScheduler()
    here = os.path.abspath(os.path.dirname(__file__))

    conf_files = sorted(glob.glob(os.path.join(here, 'conf.d', '*.ini')))
    if not conf_files:
        print('No conf.d/*.ini file found. Exiting...')
        return False

    config_vars = get_cli_config_vars()

    # python interpreter: local venv if present, else python3
    python_cmp = os.path.join(here, 'venv', 'bin', 'python3')
    if not os.path.exists(python_cmp):
        python_cmp = 'python3'

    file_agent = os.path.join(here, SCRIPT_NAME)
    if not os.path.exists(file_agent):
        print('No {} found. Exiting...'.format(SCRIPT_NAME))
        return False

    counter = 1
    offset = 0
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
            print('Skipping {}: {}'.format(config_ini, e))
            counter += 1
            continue

        per_job = dict(config_vars)
        per_job['worker_timeout'] = worker_timeout

        if counter % config_vars['group'] == 0:
            offset += config_vars['offset']
        cron_params = get_cron_params(run_interval, offset)

        scheduler.add_job(
            run_job, 'cron', (python_cmp, file_agent, config_ini, per_job),
            **cron_params, name=os.path.basename(config_ini), coalesce=True,
            misfire_grace_time=run_interval)
        print('Scheduled {} every {}s (cron={})'.format(
            os.path.basename(config_ini), run_interval, cron_params))
        counter += 1

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)


if __name__ == '__main__':
    main()
