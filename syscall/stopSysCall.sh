#!/bin/bash


function usage()
{
        echo "Usage: ./stopSysCall.sh -i SESSION_ID"
}

if [ "$#" -ne 2 ]; then
        usage
        exit 1
fi

while [ "$1" != "" ]; do
        case $1 in
                -i )    shift
                        SESSIONID=$1
                        ;;
                * )     usage
                        exit 1
        esac
        shift
done

export PATH=$PATH:/usr/local/bin
export LD_LIBRARY_PATH="/usr/local/lib"

#SESSIONID=$1
SESSIONNAME=session_$SESSIONID
BUFFERDIR=buffer/buffer_$SESSIONID
TRACEFILE=data/syscall_${SESSIONID}.log

lttng set-session $SESSIONNAME
lttng stop
babeltrace $BUFFERDIR > $TRACEFILE
lttng destroy
rm -rf $BUFFERDIR

