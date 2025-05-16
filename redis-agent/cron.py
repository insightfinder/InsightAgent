#!/usr/bin/env python
import os
import glob
import configparser
import subprocess
import pytz
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler


def run_job(python_cmp, file_agent, file_agent_log):
    subprocess.run("{} {} > {} 2>&1".format(python_cmp, file_agent, file_agent_log), shell=True)


def get_cron_params(interval_seconds):
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

    return {unit: '*/{}'.format(interval)}


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
    if len(conf_files) == 0:
        print('No config.ini file found. Exiting...')
        return False
    config_ini = conf_files[0]
    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser()
        config_parser.read_file(fp)

        run_interval = config_parser.get('insightfinder', 'run_interval')
        sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
        if run_interval.endswith('s'):
            run_interval = int(run_interval[:-1])
        else:
            run_interval = int(run_interval) * 60
        if sampling_interval.endswith('s'):
            sampling_interval = int(sampling_interval[:-1])
        else:
            sampling_interval = int(sampling_interval) * 60
        interval_seconds = run_interval or sampling_interval or interval_seconds
    # build cron params
    cron_params = get_cron_params(interval_seconds)

    # get python path
    python_cmp = os.path.abspath(os.path.join(__file__, os.pardir, './venv/bin/python3'))
    if not os.path.exists(python_cmp):
        print('No python virtual env found, using default python3')
        python_cmp = 'python3'
        #return False

    # get agent script path
    file_agent = os.path.abspath(os.path.join(__file__, os.pardir, agent_config['script_name']))
    if not os.path.exists(file_agent):
        print('No python script file found. Exiting...')
        return False

    # get log file path
    file_agent_log = os.path.abspath(os.path.join(__file__, os.pardir, 'logs/output.log'))

    # add job
    scheduler.add_job(run_job, 'cron', (python_cmp, file_agent, file_agent_log), max_instances=5, **cron_params)

    # start scheduler
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
