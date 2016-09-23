#!/bin/bash


function usage()
{
        echo "Usage: ./getSysTrace.sh -t TRACING_INTERVAL(min)"
}

if [ "$#" -ne 2 ]; then
        usage
        exit 1
fi

while [ "$1" != "" ]; do
        case $1 in
                -t )    shift
                        TRACING_INTERVAL=$1
                        ;;
                * )     usage
                        exit 1
        esac
        shift
done

export PATH=$PATH:/usr/local/bin
export LD_LIBRARY_PATH="/usr/local/lib"

INSIGHTSYSCALLDIR=`pwd`
sudo rm -rf $INSIGHTSYSCALLDIR/buffer/*
sudo rm -rf $INSIGHTSYSCALLDIR/data/*
sudo rm -rf $INSIGHTSYSCALLDIR/log/*
sudo mkdir -p $INSIGHTSYSCALLDIR/buffer
sudo mkdir -p $INSIGHTSYSCALLDIR/data
sudo mkdir -p $INSIGHTSYSCALLDIR/log
if [[ -f $INSIGHTSYSCALLDIR/log/SessionID.txt ]]
then
        sudo cp /dev/null $INSIGHTSYSCALLDIR/log/SessionID.txt
else
        sudo touch $INSIGHTSYSCALLDIR/log/SessionID.txt
fi


TEMPCRON=ifsystrace
if [[ -f $TEMPCRON ]]
then
        sudo rm $TEMPCRON
fi

#Initialize the first two SysTrace first
#sudo python initSysTrace.py -d $INSIGHTSYSCALLDIR 2>$INSIGHTSYSCALLDIR/log/systrace.err 1>$INSIGHTSYSCALLDIR/log/systrace.out 

#sleep 1m

#Then, start the regular SysTrace routine
echo "*/$TRACING_INTERVAL * * * * root python $INSIGHTSYSCALLDIR/runSysTrace.py -d $INSIGHTSYSCALLDIR 2>$INSIGHTSYSCALLDIR/log/systrace.err 1>$INSIGHTSYSCALLDIR/log/systrace.out" >> $TEMPCRON

sudo chown root:root $TEMPCRON
sudo chmod 644 $TEMPCRON
sudo mv $TEMPCRON /etc/cron.d/


