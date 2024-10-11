#!/usr/bin/env python3

import argparse
import calendar
import datetime
import requests
import sys
import time
from time import gmtime, strftime


logfile = "/var/log/localcron.log"
logging = False


def logmsg(msg):
    output = f"{strftime('%Y-%m-%d %H:%M:%S', gmtime())} [{op}] {msg}\n"
    if logging:
        log = open(logfile, "a")
        log.write(output)
        log.close()
    else:
        print(output)


def send_request(url, retry, wait, deadline):
    for i in range(0, retry):
        wait = wait * (1.5**i)
        try:
            r = requests.post(url, verify=False)
            if r.ok:
                logmsg("Succeeded:" + url)
                return r
            else:
                logmsg("Failed(response):" + url)
                time.sleep(wait)
        except requests.exceptions.RequestException as e:
            logmsg(str(e))
            time.sleep(wait)

        if datetime.datetime.now() >= deadline:
            logmsg("Failed(deadline):" + url)
            sys.exit(1)
        if i == retry - 1:
            logmsg("Failed(retry):" + url)
            sys.exit(1)


parser = argparse.ArgumentParser()
parser.add_argument("operation", help="operation")
parser.add_argument("-p", "--parameters", nargs="+", help="operation parameters")
parser.add_argument(
    "-f", "--frequency", type=int, required=True, help="cron job frequency"
)
parser.add_argument(
    "-r",
    "--retry",
    default=5,
    type=int,
    help="max retry to send request (default 5)",
)
parser.add_argument(
    "-w",
    "--wait",
    default=60,
    type=int,
    help="wait seconds between retry (default 60)",
)
parser.add_argument(
    "-u", "--url", default="https://webapp:8443", help="url of appserver"
)
args = parser.parse_args()

op = args.operation
freq = args.frequency
retry = args.retry if freq >= 600 else 1
wait = args.wait

op_params = f"?{'&'.join(args.parameters)}" if args.parameters else ""
op_url = f"{args.url}/localcron/{args.operation}{op_params}"

status_params = f"?operation={op}&frequency={freq}&updatetimestamp={calendar.timegm(gmtime()) * 1000}"
status_url = f"{args.url}/api/v1/cronstatus{status_params}"

deadline = datetime.datetime.now() + datetime.timedelta(seconds=freq)

for url in [op_url, status_url]:
    send_request(url, retry, wait, deadline)
