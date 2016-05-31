#!/bin/sh
DATADIR='data/'
cd $DATADIR
date +%s%3N | awk '{print "timestamp="$1}' > timestamp.txt & PID1=$!

grep 'cpu ' /proc/stat | awk '{print "user="$2"\nnice="$3"\nsystem="$4"\nidle="$5"\niowait="$6"\nirq="$7"\nsoftirq="$8}' > cpumetrics.txt & PID2=$!

cat /proc/diskstats | awk '{if ($3 ~ /[0-9]/) {} else {readsector+=$6;writesector+=$10}} END{print "DiskRead#MB="readsector*512/(1024*1024)"\nDiskWrite#MB="writesector*512/(1024*1024)}' > diskmetrics.txt & PID3=$!

df -k | awk '{if (NR!=1) diskusedspace += $3} END{print "DiskUsed#MB="diskusedspace/1024}' > diskusedmetrics.txt & PID4=$!

cat /proc/net/dev | awk '{NetworkBytesin+=$2;NetworkBytesout+=$10} END{print "NetworkIn#MB="NetworkBytesin/(1024*1024)"\nNetworkOut#MB="NetworkBytesout/(1024*1024)}' > networkmetrics.txt & PID5=$!

cat /proc/meminfo | grep Mem | awk '{gsub( "[:':']","=" );print}' | awk 'BEGIN{i=0} {mem[i]=$2;i=i+1} END{print "MemUsed#MB="(mem[0]-mem[1])/1024}' > memmetrics.txt & PID6=$!

wait $PID1
wait $PID2
wait $PID3
wait $PID4
wait $PID5
wait $PID6
