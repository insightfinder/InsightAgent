#!/bin/sh
DATADIR='data/'
cd $DATADIR
date +%s%3N | awk '{print "timestamp="$1}' > timestamp.txt & PID1=$!

grep cpu /proc/stat | awk '{if ($1 ~ /[0-9]/) {print $1"$user="$2"\n"$1"$nice="$3"\n"$1"$system="$4"\n"$1"$idle="$5"\n"$1"$iowait="$6"\n"$1"$irq="$7"\n"$1"$softirq="$8;}}' > cpumetrics.txt & PID2=$!

cat /proc/diskstats | awk 'BEGIN{readsector=0;writesector=0} {if ($3 ~ /[0-9]/) {} else {readsector+=$6;writesector+=$10}} END{print "DiskRead="readsector"\nDiskWrite="writesector}' > diskmetrics.txt & PID3=$!

df -k | awk 'BEGIN{diskusedspace=0}{if(NR!=1)print "DiskUsed"$6"="$3; diskusedspace += $3}END{print "DiskUsed="diskusedspace}' > diskusedmetrics.txt & PID4=$!

cat /proc/net/dev | awk 'BEGIN{NetworkBytesin=0;NetworkBytesout=0} {NetworkBytesin+=$2;NetworkBytesout+=$10} END{print "NetworkIn="NetworkBytesin"\nNetworkOut="NetworkBytesout}' > networkmetrics.txt & PID5=$!

cat /proc/meminfo | grep Mem | awk '{gsub( "[:':']","=" );print}' | awk 'BEGIN{i=0} {mem[i]=$2;i=i+1} END{print "MemUsed="(mem[0]-mem[1])}' > memmetrics.txt & PID6=$!

cat /proc/loadavg | awk '{print "LoadAvg1="$1; print "LoadAvg5="$2; print "LoadAvg15="$3}' > loadavg.txt & PID7=$!

wait $PID1
wait $PID2
wait $PID3
wait $PID4
wait $PID5
wait $PID6
wait $PID7
