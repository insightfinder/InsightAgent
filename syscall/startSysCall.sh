#!/bin/bash


function usage()
{
        echo "Usage: ./startSysCall.sh -i SESSION_ID"
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

SESSIONNAME=session_$SESSIONID
BUFFERDIR=buffer/buffer_$SESSIONID

#every internal, always start a new trace
lttng create $SESSIONNAME -o $BUFFERDIR
lttng enable-event --kernel --all --syscall
lttng add-context -k -t procname -t pid -t ppid -t tid
lttng set-session $SESSIONNAME
lttng start

