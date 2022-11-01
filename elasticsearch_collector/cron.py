#!/usr/bin/env python
import configparser
import glob
import os
import subprocess
from optparse import OptionParser

from apscheduler.schedulers.blocking import BlockingScheduler


def run_job(python_cmp, file_agent, config_ini, file_agent_log, config_vars):
    print("Start {}".format(config_ini))
    if 'process' in config_vars.keys():
        subprocess.run(
            f"{python_cmp} {file_agent} {config_vars['log_level']} -p {config_vars['process']} -c {config_ini} --timeout={config_vars['worker_timeout']}  2>&1",
            shell=True)
    else:
        subprocess.run(
            f"{python_cmp} {file_agent} {config_vars['log_level']} -c {config_ini} --timeout={config_vars['worker_timeout']} 2>&1",
            shell=True)


def get_cron_params(interval_seconds, offset):
    unit = 'second'
    interval = interval_seconds
    if interval >= 60:
        interval = int(interval / 60)
        unit = 'minute'
    if interval >= 60:
        interval = int(interval / 60)
        unit = 'hour'
    if interval >= 24:
        interval = int(interval / 24)
        unit = 'day'

    if interval == 'second':
        return {unit: '*/{}'.format(interval + offset)}
    else:
        return {unit: '*/{}'.format(interval), 'second': '{}'.format(offset)}


def get_cli_config_vars():
    """ get CLI options. use of these options should be rare """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    """
    """
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-g', '--group', action='store', dest='group_size', default=3,
                      help='Number of config files to run in group')
    parser.add_option('-o', '--offset', action='store', dest='offset', default=3,
                      help='Offset in seconds')
    parser.add_option('-p', '--process', action='store', dest='process',
                      help='Number of processes for each agent to use for multithreading')
    (options, args) = parser.parse_args()

    config_vars = {
        'group': int(options.group_size),
        'offset': int(options.offset),
        'log_level': ""
    }

    if options.process:
        config_vars['process'] = options.process

    if options.verbose:
        config_vars['log_level'] = "-v"
    elif options.quiet:
        config_vars['log_level'] = "-q"

    return config_vars


def main():
    scheduler = BlockingScheduler()

    # get agent.txt
    file_ini = os.path.abspath(os.path.join(__file__, os.pardir, "agent.txt"))
    if not os.path.exists(file_ini):
        print('No agent.txt file found. Exiting...')
        return False
    agent_config = {}
    with open(file_ini, 'r') as f:
        try:
            for line in f.read().split('\n'):
                data = [x.strip() for x in line.split('=') if x.strip()]
                if len(data) > 1:
                    agent_config[data[0]] = data[1]
        except Exception as e:
            print(e)
    if not agent_config['script_name']:
        return False

    # get job info
    # get interval
    interval_seconds = 60
    conf_path = os.path.abspath(os.path.join(__file__, os.pardir, 'conf.d/*.ini'))
    conf_files = glob.glob(conf_path)
    config_vars = get_cli_config_vars()
    if len(conf_files) == 0:
        print('No config.ini file found. Exiting...')
        return False

    # Set up offset
    counter = 1
    offset = 0

    # start every config file as cron job
    for config_ini in conf_files:
        with open(config_ini) as fp:
            config_parser = configparser.ConfigParser()
            config_parser.read_file(fp)

            run_interval = config_parser.get('insightfinder', 'run_interval')
            worker_timeout = config_parser.get('insightfinder', 'worker_timeout')
            sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
            if run_interval.endswith('s'):
                run_interval = int(run_interval[:-1])
            else:
                run_interval = int(run_interval) * 60
            if not worker_timeout:
                worker_timeout = run_interval
            else:
                if worker_timeout.endswith('s'):
                    worker_timeout = int(worker_timeout[:-1])
                else:
                    worker_timeout = int(worker_timeout) * 60
            config_vars['worker_timeout'] = worker_timeout

            if sampling_interval.endswith('s'):
                sampling_interval = int(sampling_interval[:-1])
            else:
                sampling_interval = int(sampling_interval) * 60
            interval_seconds = run_interval or sampling_interval or interval_seconds

        # increment the offset every 4 config files ** Hardcoded for now
        if counter % config_vars['group'] == 0:
            offset += config_vars['offset']

        # build cron params
        cron_params = get_cron_params(interval_seconds, offset)

        # get python path
        python_cmp = os.path.abspath(os.path.join(__file__, os.pardir, './venv/bin/python3'))
        if not os.path.exists(python_cmp):
            print('No python virtual env found. Exiting...')
            return False

        # get agent script path
        file_agent = os.path.abspath(os.path.join(__file__, os.pardir, agent_config['script_name']))
        if not os.path.exists(file_agent):
            print('No python script file found. Exiting...')
            return False

        # get log file path
        config_filename = os.path.basename(config_ini)
        file_agent_log = os.path.abspath(os.path.join(__file__, os.pardir, f'output-{config_filename}.log'))

        # add job
        scheduler.add_job(run_job, 'cron', (python_cmp, file_agent, config_ini, file_agent_log, config_vars),
                          **cron_params, name=config_filename)

        # increment counter
        counter += 1

    # start scheduler
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
