#!/bin/bash
# Invoked by cron every 30 minutes; runs one health-check pass and exits.
cd "$(dirname "$0")" || exit 1
./ServiceNowMonitor -config configs/config.yaml
