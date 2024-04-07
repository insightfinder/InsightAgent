import configparser
import os

import arrow

from utils import config_error

CONFIG_SECTION = 'centerity'


def get_agent_config_vars(logger, config_ini):
    """ Read and parse agent config"""
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False

    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser()
        config_parser.read_file(fp)

        try:
            request_timeout = config_parser.get(CONFIG_SECTION, 'request_timeout', raw=True, fallback='60')

            target_timestamp_timezone = config_parser.get(CONFIG_SECTION, 'target_timestamp_timezone', raw=True,
                                                          fallback='UTC')

            if request_timeout and len(request_timeout) != 0:
                request_timeout = int(request_timeout)
            else:
                request_timeout = 60

            if target_timestamp_timezone and len(target_timestamp_timezone) != 0:
                target_timestamp_timezone = int(arrow.now(target_timestamp_timezone).utcoffset().total_seconds())
            else:
                config_error(logger, 'target_timestamp_timezone')

            # proxies
            agent_http_proxy = config_parser.get(CONFIG_SECTION, 'agent_http_proxy', fallback=None)
            agent_https_proxy = config_parser.get(CONFIG_SECTION, 'agent_https_proxy', fallback=None)

        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger, )

        config_vars = {'request_timeout': request_timeout, 'target_timestamp_timezone': target_timestamp_timezone,
                       'agent_http_proxy': agent_http_proxy, 'agent_https_proxy': agent_https_proxy, }

        return config_vars
