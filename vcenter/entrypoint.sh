#!/bin/env bash
export AGENT_RUN_INTERVAL=${AGENT_RUN_INTERVAL:-1}
echo "AGENT_RUN_INTERVAL: ${AGENT_RUN_INTERVAL}m"
set -e

# Test the agent
echo "Test agent"
python3 vCenter.py -t

# Start the agent cron
echo "Start agent cron..."
while true; do
    python3 vCenter.py &
    sleep "${AGENT_RUN_INTERVAL}m"
done