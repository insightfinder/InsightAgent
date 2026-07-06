#!/bin/bash
# Simple cron watchdog: checks if send_metrics.py is running, starts it if not.
#
# Crontab example (checks every 5 minutes):
#   */5 * * * * /path/to/telrad-agent/monitor.sh

cd "$(dirname "$0")" || exit 1

if ! pgrep -f "send_metrics.py" > /dev/null; then
    echo "$(date): send_metrics.py not running, starting it" >> monitor.log
    nohup python3 send_metrics.py >> agent.log 2>&1 &
fi
