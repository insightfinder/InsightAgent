#!/usr/bin/env bash
#=========================================#
# This script will serve as the entrypoint
# of the Dell PowerCollecteor Agent.
# It will run the agent every 5 minutes
#=========================================#

# Main Loop
echo "Start PowerAgent Cron..."
while true; do
    /root/powerAgent/dell_power_collector
    sleep 300
done