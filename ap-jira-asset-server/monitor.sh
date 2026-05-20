#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_UVICORN="$SCRIPT_DIR/venv/bin/uvicorn"
APP_MODULE="src.main:app"
HOST="0.0.0.0"
PORT="80"
SERVER_LOG="$SCRIPT_DIR/server.log"
MONITOR_LOG="$SCRIPT_DIR/monitor.log"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

is_running() {
    pgrep -f "uvicorn ${APP_MODULE}" > /dev/null 2>&1
}

if is_running; then
    echo "[$TIMESTAMP] Server is running. No action needed." >> "$MONITOR_LOG"
else
    echo "[$TIMESTAMP] Server is NOT running. Starting..." >> "$MONITOR_LOG"
    cd "$SCRIPT_DIR"
    nohup "$VENV_UVICORN" "$APP_MODULE" --host "$HOST" --port "$PORT" >> "$SERVER_LOG" 2>&1 &
    sleep 2
    if is_running; then
        echo "[$TIMESTAMP] Server started successfully (PID: $(pgrep -f "uvicorn ${APP_MODULE}"))." >> "$MONITOR_LOG"
    else
        echo "[$TIMESTAMP] ERROR: Server failed to start. Check $SERVER_LOG for details." >> "$MONITOR_LOG"
    fi
fi
