#!/bin/bash

export PATH=$PATH:/usr/local/bin
export LD_LIBRARY_PATH="/usr/local/lib"

lttng destroy --all
rm -rf buffer/*
rm -rf data/*
cp /dev/null log/SessionID.txt
#pkill -f lttng
rm -rf /etc/cron.d/ifsystrace
