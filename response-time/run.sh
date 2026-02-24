#!/bin/bash

# Read sleep interval from config.ini
SLEEP_INTERVAL=$(grep "^sleep_interval" config.ini | cut -d '=' -f 2 | xargs)

# Default to 120 seconds if not found in config
SLEEP_INTERVAL=${SLEEP_INTERVAL:-120}

while true; do
       python3 main.py &
       sleep "$SLEEP_INTERVAL"
done