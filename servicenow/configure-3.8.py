#!/usr/bin/env python
from optparse import OptionParser
import os
import fileinput
import sys
import shutil
import ifobfuscate


def prompt(option, default='', silent=False):
    """ prompt for input using /dev/tty. inspired by getpass """
    def tell_value(prompt, value):
        return '\033[F{}{}\n'.format(prompt, value)

    prompt = '{}: '.format(option) if not default else '{} [Default: {}]: '.format(option, default)
    # open /dev/tty
    with open('/dev/tty', mode='w+', buffering=1) as stream:
        # ask the question
        stream.write(prompt)
        stream.flush()
        # get the input
        if silent:
            os.system('stty -echo')
        value = stream.readline().strip()
        stream.flush()
        if silent:
            os.system('stty sane')
            stream.write('\n')
        # if no given value, let the user know the default will be used
        if not value and default:
            value = default
            stream.write(tell_value(prompt, value))
        # if value given and output was silent, obfuscate the output then give it
        elif value and silent:
            value = str(ifobfuscate.obfuscate(value))
            stream.write(tell_value(prompt, value))
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
            default = line.partition('=')[2].strip()
            value = prompt(option, default, silent=option.endswith(encrypted_str))
            line = '{} = {}\n'.format(option, value)
        # write line to config file
        sys.stdout.write(line)
        sys.stdout.flush()

