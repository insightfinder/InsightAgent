import subprocess
import logging
import os
from optparse import OptionParser


def get_config_file_name(user_name):
    return user_name + '.ini'


def save_config_file(config_file_name, config):
    with open(config_file_name, 'w') as config_file:
        config.write(config_file)
    config_file.close()


def logging_setting():
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=logging.INFO,
        filename='log.out',
        datefmt='%Y-%m-%d %H:%M:%S')


def get_username():
    parser = OptionParser(usage="Usage: %prog [options]")
    parser.add_option("-u", "--user_name",
                      action="store", dest="user_name", help="User account's name")
    (options, args) = parser.parse_args()
    return options.user_name


def run_command(command):
    logging_setting()
    subprocess.Popen(command, cwd=os.getcwd(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    logging.info("Running command: " + command)
