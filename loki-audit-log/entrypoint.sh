#!/bin/bash
crond &
tail -f /var/log/cron.log