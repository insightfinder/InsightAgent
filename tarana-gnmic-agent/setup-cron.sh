#!/bin/bash

# Tarana gNMIc Agent - Cron Setup Script
# This script sets up a cron job to monitor and restart services if they stop

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "========================================================"
echo "Tarana gNMIc Agent - Cron Setup"
echo "========================================================"

# Create monitor script
cat > monitor.sh << 'EOF'
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
EOF

chmod +x monitor.sh

echo -e "${GREEN}✓ Monitor script created: monitor.sh${NC}"
echo ""

# Add to crontab
echo -e "${YELLOW}Do you want to add a cron job to run the monitor every 5 minutes? (y/n)${NC}"
read -r response

if [[ "$response" =~ ^[Yy]$ ]]; then
    # Check if cron job already exists
    if crontab -l 2>/dev/null | grep -q "tarana-gnmic-agent/monitor.sh"; then
        echo -e "${YELLOW}Cron job already exists${NC}"
    else
        # Add cron job
        (crontab -l 2>/dev/null; echo "*/5 * * * * cd $SCRIPT_DIR && ./monitor.sh") | crontab -
        echo -e "${GREEN}✓ Cron job added successfully${NC}"
        echo ""
        echo "The monitor script will run every 5 minutes and:"
        echo "  - Check if services are running"
        echo "  - Restart any stopped services"
        echo "  - Log all actions to logs/monitor.log"
        echo ""
        echo "Current crontab:"
        crontab -l | grep "tarana-gnmic-agent"
    fi
else
    echo -e "${YELLOW}Cron job not added${NC}"
    echo ""
    echo "To manually run the monitor:"
    echo "  ./monitor.sh"
    echo ""
    echo "To add to cron later, run:"
    echo "  (crontab -l; echo '*/5 * * * * cd $SCRIPT_DIR && ./monitor.sh') | crontab -"
fi

echo ""
echo "========================================================"
echo -e "${GREEN}Setup completed!${NC}"
echo ""
echo "Monitor script: ./monitor.sh"
echo "Monitor logs:   tail -f logs/monitor.log"
echo ""
echo "To remove the cron job later:"
echo "  crontab -e  (then delete the line)"
echo "========================================================"
