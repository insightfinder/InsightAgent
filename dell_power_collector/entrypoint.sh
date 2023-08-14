#!/usr/bin/env bash
#=========================================#
# This script will serve as the entrypoint
# of the Dell PowerCollecteor Agent.
# It will run the agent every 5 minutes by default
#=========================================#
set -e

# Setup run interval
export AGENT_RUN_INTERVAL=${AGENT_RUN_INTERVAL:-300}
echo "AGENT_RUN_INTERVAL: ${AGENT_RUN_INTERVAL}"

cd /root/powerAgent

# Copy file from configMaps
if [ -d "configMap-config-ini" ]; then
    echo "Copy ini configurations to conf.d/"
    cp -v -f configMap-config-ini/* conf.d/
fi

if [ -d "configMap-config-json" ]; then
    echo "Copy json configurations to conf.d/"
    cp -v -f configMap-config-json/* conf.d/
fi

# Auto import SSL certificates
update-ca-trust

# Test connection by running the agent for one time
./dell_power_collector
sleep "${AGENT_RUN_INTERVAL}m"

# Main Loop
echo "Start PowerAgent Cron..."
while true; do
    ./dell_power_collector &
    sleep "${AGENT_RUN_INTERVAL}m"
done