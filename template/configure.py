#!/usr/bin/env python
from optparse import OptionParser
import os
import io
import contextlib
import fileinput
import getpass
import sys
import shutil
import ifobfuscate


def overwrite_line(newline):
    return '\033[F{}\n'.format(newline)


def prompt(option, default=''):
    """ prompt for input using /dev/tty. inspired by getpass """
    prompt = u'{}: '.format(option) if not default else u'{} [Defualt: {}]: '.format(option, default)
    # open /dev/tty
    with open('/dev/tty', mode='w+', buffering=1) as stream:
        # ask the question
        stream.write(prompt)
        stream.flush()
        # get the input
        value = stream.readline().strip()
        # if no given value, let the user know the default will be used
        if not value and default:
            value = default
            stream.write(overwrite_line('{}{}'.format(prompt, value)))
        stream.flush()
    return value


def get_config_ini():
    """ get config file from cli option """
    parser = OptionParser()
    parser.add_option('-c', '--config', action='store', dest='config', default='config.ini',
                      help='Path to the config file to use. Defaults to config.ini')
    (options, args) = parser.parse_args()
    if not os.path.isfile(options.config):
        shutil.copyfile('./config.ini.template', options.config)
    return options.config


if __name__ == "__main__":
    """ put obfuscated strings into config file """
    encrypted_str = ifobfuscate.decode('X2VuY3J5cHRlZA==')
    config_ini = get_config_ini()

    # read config
    for line in fileinput.input(config_ini, inplace=True):
        # check if a non-comment line
        if len(line) != 0 and not line.startswith('#') and not line.startswith('[') and '=' in line:
            # check if an encrypted option
            option = line.partition('=')[0].strip()
            if option.endswith(encrypted_str):
                try:
                    # ask for value
                    value = getpass.getpass(prompt='{}: '.format(option))
                    # encode
                    value = ifobfuscate.obfuscate(value)
                    # write to /dev/tty
                    with open('/dev/tty', mode='w+', buffering=1) as stream:
                        stream.write(overwrite_line('{}: {}'.format(option, value)))
                        stream.flush()
                except Exception as e:
                    value = ''
            else:
                default = line.partition('=')[2].strip()
                value = prompt(option, default)
            line = '{} = {}\n'.format(option, value)
        # write line to config file
        sys.stdout.write(line)
        sys.stdout.flush()

