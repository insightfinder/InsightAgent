#!/usr/bin/env python
from optparse import OptionParser
import base64
import os
import fileinput
import getpass
import sys

def decode(obfuscated):
    """ decode an obfuscated string """
    return base64.b64decode(obfuscated).decode('utf-8')


def obfuscate(to_obfuscate):
    """ obfuscate a string """
    return base64.b64encode(to_obfuscate).encode('utf-8')


if __name__ == "__main__":
    """ put obfuscated strings into config file """
    encrypted_str = decode('X2VuY3J5cHRlZA==')
    # get config file from cli option
    parser = OptionParser()
    parser.add_option('-c', '--config', action='store', dest='config', default='config.ini',
                      help='Path to the config file to use. Defaults to config.ini')
    (options, args) = parser.parse_args()
    config_ini = options.config if os.path.isfile(options.config) else os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini'))

    # read config
    for line in fileinput.input(config_ini, inplace=True):
        # check if a non-comment line
        if len(line) != 0 and not line.startswith('#'):
            # check if an encrypted option
            option = line.partition('=')[0].strip()
            if option.endswith(encrypted_str):
                option_short = option.partition(encrypted_str)[0]
                try:
                    # ask for value
                    value = getpass.getpass(prompt='{}: '.format(option_short))
                    # encode
                    value = obfuscate(value)
                except Exception as e:
                    value = ''
                finally:
                    line = '{} = {}\n'.format(option, value)
        sys.stdout.write(line)
