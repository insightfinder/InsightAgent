#!/bin/sh
while true; do
  echo "$(date): Running webhook-app"
  /app/webhook-app &
  echo "$(date): Sleeping for ${SCHEDULE_INTERVAL:-600} seconds"
  sleep ${SCHEDULE_INTERVAL:-600}
done