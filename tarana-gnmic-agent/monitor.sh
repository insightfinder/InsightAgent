#!/bin/bash

# Tarana gNMIc Agent - Monitor Script
# This script checks if services are running and restarts them if needed

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

LOG_FILE="logs/monitor.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to check if process is running
is_running() {
    if [ -f "$1" ]; then
        pid=$(cat "$1")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

log "=== Monitor check started ==="

# Check if any service is down and restart all via start.sh
needs_restart=false

# Check InfluxDB
if ! docker ps | grep -q influxdb; then
    log "WARNING: InfluxDB is not running"
    needs_restart=true
fi

# Check gNMIc
if ! is_running "gnmic/gnmic.pid" && ! pgrep -f "gnmicc listen" > /dev/null; then
    log "WARNING: gNMIc is not running"
    needs_restart=true
fi

# Check Agent
if ! is_running "agent.pid"; then
    log "WARNING: Agent is not running"
    needs_restart=true
fi

# Restart services if needed
if [ "$needs_restart" = true ]; then
    log "Restarting services via start.sh..."
    ./start.sh >> "$LOG_FILE" 2>&1
    log "Services restarted"
else
    log "All services are running"
fi

log "=== Monitor check completed ==="
