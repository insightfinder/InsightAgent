#!/bin/bash

# Tarana gNMIc Agent - Start Script
# This script starts all services: InfluxDB, gNMIc, and the agent

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "========================================================"
echo "Tarana gNMIc Agent - Starting Services"
echo "========================================================"

# Function to check if a process is running
is_running() {
    if [ -f "$1" ]; then
        pid=$(cat "$1")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# 1. Start InfluxDB (Docker)
echo -e "\n${YELLOW}[1/3] Starting InfluxDB...${NC}"
cd influxdb
if docker ps | grep -q influxdb; then
    echo -e "${GREEN}✓ InfluxDB is already running${NC}"
else
    docker-compose up -d
    echo -e "${GREEN}✓ InfluxDB started${NC}"
    echo "   Waiting for InfluxDB to be ready..."
    sleep 5
fi
cd ..

# 2. Start gNMIc telemetry listener
echo -e "\n${YELLOW}[2/3] Starting gNMIc telemetry listener...${NC}"
if is_running "gnmic/gnmic.pid"; then
    echo -e "${GREEN}✓ gNMIc is already running (PID: $(cat gnmic/gnmic.pid))${NC}"
else
    cd gnmic
    nohup sudo ./gnmicc listen --address :80 --org tarana --config telemetry_cfg.yaml > ../logs/gnmic.log 2>&1 &
    echo $! > gnmic.pid
    echo -e "${GREEN}✓ gNMIc started (PID: $!)${NC}"
    cd ..
fi

# 3. Start the agent
echo -e "\n${YELLOW}[3/3] Starting Tarana gNMIc Agent...${NC}"
if is_running "agent.pid"; then
    echo -e "${GREEN}✓ Agent is already running (PID: $(cat agent.pid))${NC}"
else
    # Build the agent if binary doesn't exist
    if [ ! -f "tarana-gnmic-agent" ]; then
        echo "   Building agent..."
        go build -o tarana-gnmic-agent
    fi
    
    nohup ./tarana-gnmic-agent --config config/config.yaml > logs/nohup.log 2>&1 &
    echo $! > agent.pid
    echo -e "${GREEN}✓ Agent started (PID: $!)${NC}"
fi

echo -e "\n========================================================
"
echo -e "${GREEN}All services started successfully!${NC}"
echo ""
echo "Service Status:"
echo "  - InfluxDB:  http://localhost:9092"
echo "  - gNMIc:     Listening on port 80"
echo "  - Agent:     Running (logs/nohup.log)"
echo ""
echo "Logs:"
echo "  - Agent:     tail -f logs/nohup.log"
echo "  - Agent Log: tail -f logs/agent.log"
echo "  - gNMIc:     tail -f logs/gnmic.log"
echo ""
echo "========================================================"
