#!/bin/bash


function usage()
{
        echo "Usage: ./stopSysCall.sh -i SESSION_ID -l Language [java/c/c++]"
}

if [ "$#" -ne 4 ]; then
        usage
        exit 1
fi

while [ "$1" != "" ]; do
        case $1 in
                -i )    shift
                        SESSIONID=$1
                        ;;
                -l )    shift
                        LANGUAGE=$1
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
if [ $LANGUAGE = "java" ]; then
        babeltrace --clock-date $BUFFERDIR > $TRACEFILE
fi
if [ $LANGUAGE = "c" ] || [ $LANGUAGE = "cpp" ]; then
        babeltrace $BUFFERDIR > $TRACEFILE
fi
lttng destroy
rm -rf $BUFFERDIR
