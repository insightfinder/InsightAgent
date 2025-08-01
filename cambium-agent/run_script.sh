#!/bin/bash

AGENT_BINARY="/opt/insight-agent/cambium-agent/cambiumAgent"
AGENT_WORKDIR="/opt/insight-agent/cambium-agent"

if pgrep -f "cambiumAgent" > /dev/null; then
    exit 0
else
    cd "$AGENT_WORKDIR"
    nohup "$AGENT_BINARY" > nohup.out 2>&1 &
fi