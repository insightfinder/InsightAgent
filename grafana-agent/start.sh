#!/bin/bash

# Check if GRAFANA_AGENT_INTERVAL is set in the environment
if [ -z "$GRAFANA_AGENT_INTERVAL" ]; then
  GRAFANA_AGENT_INTERVAL=60 # Unit: seconds
fi

# Check if GRAFANA_AGENT_PATH is set in the environment
if [ -z "$GRAFANA_AGENT_PATH" ]; then
  GRAFANA_AGENT_PATH="$(pwd)/grafana-agent"
fi
GRAFANA_AGENT_DIR=$(dirname "$GRAFANA_AGENT_PATH")

# Run the agent
cd $GRAFANA_AGENT_DIR
while true; do
  $GRAFANA_AGENT_PATH &
  sleep $GRAFANA_AGENT_INTERVAL
done