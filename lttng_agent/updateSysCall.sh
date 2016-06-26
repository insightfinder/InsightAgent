#!/bin/bash


function usage()
{
        echo "Usage: ./updateSysCall.sh -o OLD_SESSION_ID -c CURRENT_SESSION_ID -n NEW_SESSION_ID"
}

if [ "$#" -ne 6 ]; then
        usage
        exit 1
fi

while [ "$1" != "" ]; do
        case $1 in
                -o )    shift
                        oldSESSIONID=$1
                        ;;
                -c )    shift
                        currentSESSIONID=$1
                        ;;
                -n )    shift
                        newSESSIONID=$1
                        ;;
                * )     usage
                        exit 1
        esac
        shift
done

export PATH=$PATH:/usr/local/bin
export LD_LIBRARY_PATH="/usr/local/lib"

newSESSIONNAME=session_$newSESSIONID
newBUFFERDIR=buffer/buffer_$newSESSIONID

#every internal, always start a new trace
lttng create $newSESSIONNAME -o $newBUFFERDIR
lttng enable-event --kernel --all --syscall
lttng add-context -k -t procname -t pid -t ppid -t tid
#lttng set-session $newSESSIONNAME
lttng start

if [ $currentSESSIONID != "null" ]
then
    currentSESSIONNAME=session_$currentSESSIONID
    currentBUFFERDIR=buffer/buffer_$currentSESSIONID
    #every internal, always stop the current trace  2x-internal-ago trace
    lttng set-session $currentSESSIONNAME
    lttng stop
    lttng destroy
fi

if [ $oldSESSIONID != "null" ]
then
    oldSESSIONNAME=session_$oldSESSIONID
    oldBUFFERDIR=buffer/buffer_$oldSESSIONID
    #every interval, always delete the 2x-internal-ago trace buffer
    #babeltrace --clock-date $oldBUFFERDIR > $oldTRACEFILE
    sudo rm -rf $oldBUFFERDIR
fi
