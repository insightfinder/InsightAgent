#!/bin/bash

AGENT_BINARY="{path}/EdgecoreAgent"
AGENT_WORKDIR="{path}"

if pgrep -f "EdgecoreAgent" > /dev/null; then
    exit 0
else
    cd "$AGENT_WORKDIR"
    nohup "$AGENT_BINARY" > nohup.out 2>&1 &
fi