#!/bin/bash

# Tarana gNMIc Agent - Stop Script
# This script stops all services: Agent, gNMIc, and InfluxDB

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "========================================================"
echo "Tarana gNMIc Agent - Stopping Services"
echo "========================================================"

# Function to stop a process by PID file
stop_process() {
    local pid_file=$1
    local name=$2
    
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -e "${YELLOW}Stopping $name (PID: $pid)...${NC}"
            kill "$pid"
            
            # Wait for process to stop (max 10 seconds)
            for i in {1..10}; do
                if ! ps -p "$pid" > /dev/null 2>&1; then
                    break
                fi
                sleep 1
            done
            
            # Force kill if still running
            if ps -p "$pid" > /dev/null 2>&1; then
                echo -e "${YELLOW}Force stopping $name...${NC}"
                kill -9 "$pid"
            fi
            
            echo -e "${GREEN}✓ $name stopped${NC}"
        else
            echo -e "${YELLOW}$name is not running${NC}"
        fi
        rm -f "$pid_file"
    else
        echo -e "${YELLOW}$name PID file not found${NC}"
    fi
}

# 1. Stop the agent
echo -e "\n${YELLOW}[1/3] Stopping Tarana gNMIc Agent...${NC}"
stop_process "agent.pid" "Agent"

# 2. Stop gNMIc
echo -e "\n${YELLOW}[2/3] Stopping gNMIc telemetry listener...${NC}"
stop_process "gnmic/gnmic.pid" "gNMIc"

# Also try to stop by process name if PID file didn't work
if pgrep -f "gnmicc listen" > /dev/null; then
    echo -e "${YELLOW}Found gNMIc process, stopping...${NC}"
    sudo pkill -f "gnmicc listen" || true
    echo -e "${GREEN}✓ gNMIc stopped${NC}"
fi

# 3. Stop InfluxDB (Docker)
echo -e "\n${YELLOW}[3/3] Stopping InfluxDB...${NC}"
cd influxdb
if docker ps | grep -q influxdb; then
    docker-compose down
    echo -e "${GREEN}✓ InfluxDB stopped${NC}"
else
    echo -e "${YELLOW}InfluxDB is not running${NC}"
fi
cd ..

echo -e "\n========================================================"
echo -e "${GREEN}All services stopped successfully!${NC}"
echo "========================================================"
