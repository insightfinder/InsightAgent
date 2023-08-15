#!/bin/env bash
set -e

# Setup
cd /opt/app-root/src/
source venv/bin/activate

# Run Agent Test to verify configureation.
python event_push.py -t

# Run Agent
echo "Waiting for agent next cron..." > output.log
nohup python cron.py > nohup.log &

# Stream logs to stdout
tail -F output.log