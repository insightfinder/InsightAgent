#!/bin/bash

# Tarana gNMIc Agent - Status Script
# This script checks the status of all services

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "========================================================"
echo "Tarana gNMIc Agent - Service Status"
echo "========================================================"

# Function to check process status
check_status() {
    local pid_file=$1
    local name=$2
    
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ $name is running${NC} (PID: $pid)"
            return 0
        else
            echo -e "${RED}✗ $name is not running${NC} (stale PID file)"
            return 1
        fi
    else
        echo -e "${RED}✗ $name is not running${NC} (no PID file)"
        return 1
    fi
}

# Check InfluxDB
echo -e "\n${YELLOW}[1/3] InfluxDB Status:${NC}"
if docker ps | grep -q influxdb; then
    container_id=$(docker ps | grep influxdb | awk '{print $1}')
    echo -e "${GREEN}✓ InfluxDB is running${NC} (Container: $container_id)"
    echo "   URL: http://localhost:9092"
else
    echo -e "${RED}✗ InfluxDB is not running${NC}"
fi

# Check gNMIc
echo -e "\n${YELLOW}[2/3] gNMIc Status:${NC}"
if check_status "gnmic/gnmic.pid" "gNMIc"; then
    echo "   Listening on port 80"
elif pgrep -f "gnmicc listen" > /dev/null; then
    pid=$(pgrep -f "gnmicc listen")
    echo -e "${YELLOW}! gNMIc is running${NC} (PID: $pid, but no PID file)"
fi

# Check Agent
echo -e "\n${YELLOW}[3/3] Agent Status:${NC}"
check_status "agent.pid" "Tarana gNMIc Agent"

# Show recent log entries
echo -e "\n========================================================"
echo -e "${YELLOW}Recent Agent Logs (last 10 lines):${NC}"
echo "========================================================
"
if [ -f "logs/nohup.log" ]; then
    tail -n 10 logs/nohup.log
else
    echo "No logs found"
fi

echo -e "\n========================================================"
echo "To view live logs, run:"
echo "  tail -f logs/nohup.log      # Main output"
echo "  tail -f logs/agent.log       # Agent log file"
echo "  tail -f logs/gnmic.log       # gNMIc log file"
echo "========================================================"
