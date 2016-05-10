#!/usr/bin/python

import pexpect
import sys
import time
import os
from pexpect import pxssh
import getpass
import getopt
import argparse
import re

def sshInstall(retry):
    global user
    global host
    global password
    global user_insightfinder
    global license_key
    global sampling_interval
    global reporting_interval
    global expectations
    if retry == 0:
        return False

    expectations = ['password for %s: '%user,
          'continue (yes/no)?',
           pexpect.EOF,
           pexpect.TIMEOUT,
           'Name or service not known',
           'Permission denied',
           'No such file or directory',
           'No route to host',
           'Network is unreachable',
           'failure in name resolution',
           'No space left on device'
          ]
    try:
        s = pxssh.pxssh()
        s.login (host, user, password, original_prompt='[#$]')
        s.sendline ('sudo rm -rf insightagent* InsightAgent-master')
        res = s.expect( expectations )
        #res = s.expect(["Password:", pexpect.EOF, pexpect.TIMEOUT])
        if res == 0:
            s.sendline(password)
        if res >= 4:
            s.prompt()
            s.logout()
            return sshInstall(retry-1)
        s.prompt()
        print(s.before)
        s.sendline ('wget --no-check-certificate https://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz')
        s.prompt()         
        print(s.before)
        s.sendline ('tar xzvf insightagent.tar.gz')       # run a command
        s.prompt()                    # match the prompt
        print(s.before)               # print everything before the prompt.
        s.logout()
        return True
    except pxssh.ExceptionPxssh as e:
        print(e)
        if 'synchronize with original prompt' in str(e):
            time.sleep(1)
            return sshInstall(retry-1)
        else:
            return False


def get_args():
    parser = argparse.ArgumentParser(
        description='Script retrieves arguments for insightfinder agent.')
    parser.add_argument(
        '-n', '--USER_NAME_IN_HOST', type=str, help='User Name in Hosts', required=True)
    parser.add_argument(
        '-u', '--USER_NAME_IN_INSIGHTFINDER', type=str, help='User Name in Insightfinder', required=True)
    parser.add_argument(
        '-k', '--LICENSE_KEY', type=str, help='License key of an agent project', required=True)
    parser.add_argument(
        '-s', '--SAMPLING_INTERVAL_MINUTE', type=str, help='Sampling Interval Minutes', required=True)
    parser.add_argument(
        '-r', '--REPORTING_INTERVAL_MINUTE', type=str, help='Reporting Interval Minutes', required=True)
    parser.add_argument(
        '-p', '--PASSWORD', type=str, help='Password for hosts', required=True)
    args = parser.parse_args()
    user = args.USER_NAME_IN_HOST
    user_insightfinder = args.USER_NAME_IN_INSIGHTFINDER
    license_key = args.LICENSE_KEY
    sampling_interval = args.SAMPLING_INTERVAL_MINUTE
    reporting_interval = args.REPORTING_INTERVAL_MINUTE
    password = args.PASSWORD
    return user, user_insightfinder, license_key, sampling_interval, reporting_interval, password


if __name__ == '__main__':
    global user
    global host
    global password
    global hostfile
    global user_insightfinder
    global license_key
    global sampling_interval
    global reporting_interval
    hostfile="hostlist.txt"
    user, user_insightfinder, license_key, sampling_interval, reporting_interval, password = get_args()
    stat=True
    try:
        with open(os.getcwd()+"/"+hostfile, 'rb') as f:
            while True:
                line = f.readline()
                if line:
                    host=line.split("\n")[0]
                    print "Start installing agent in", host, "..."
                    stat = sshInstall(3)
                    if stat:
                        print "Install Succeed in", host
                    else:
                        print "Install Fail in", host
                else:
                    break
    except (KeyboardInterrupt, SystemExit):
        print "Keyboard Interrupt!!"
        sys.exit()
    except IOError as e:
        print "I/O error({0}): {1}: {2}".format(e.errno, e.strerror, e.filename)
        sys.exit()
