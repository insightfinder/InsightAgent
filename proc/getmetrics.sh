#!/bin/bash
DATADIR='data/'
cd $DATADIR

# Get timestamp
date +%s%3N | awk '{print "timestamp="$1}' > timestamp.txt & PID1=$!

# Get CPU metrics
grep cpu /proc/stat | awk '{if ($1 ~ /[0-9]$/) {print $1"$user="$2"\n"$1"$nice="$3"\n"$1"$system="$4"\n"$1"$idle="$5"\n"$1"$iowait="$6"\n"$1"$irq="$7"\n"$1"$softirq="$8;}}' > cpumetrics.txt & PID2=$!

# Get Disk metrics
cat /proc/diskstats | awk 'BEGIN{readsector=0;writesector=0} {if ($3 ~ /[0-9]/) {} else {readsector+=$6;writesector+=$10}} END{print "DiskRead="readsector"\nDiskWrite="writesector}' > diskmetrics.txt & PID3=$!

# Get Filesystem metrics
df -k | awk 'BEGIN{diskusedspace=0; disktotal=0;}{if(NR==2) disktotal = $3*100/$2}{if(NR!=1)print "DiskUsed"$6"="$3  ; diskusedspace += $3}END{print "DiskUsed="disktotal}' > diskusedmetrics.txt & PID4=$!

# Get Summary Network metrics
cat /proc/net/dev | awk 'BEGIN{NetworkBytesin=0;NetworkBytesout=0} {NetworkBytesin+=$2;NetworkBytesout+=$10} END{print "NetworkIn="NetworkBytesin"\nNetworkOut="NetworkBytesout}' > networkmetrics.txt & PID5=$!

# Get Memory metrics
cat /proc/meminfo | grep Mem | awk '{gsub( "[:':']","=" );print}' | awk 'BEGIN{i=0} {mem[i]=$2;i=i+1} END{print "MemUsed="(mem[0]-mem[1])"\nMemTotal="(mem[0])}' > memmetrics.txt & PID6=$!

# Get Shared Memory metrics
cat /proc/meminfo | grep Shmem | awk '{gsub( "[:':']","=" );print}' | awk 'BEGIN{i=0} {mem[i]=$2;i=i+1} END{print "SharedMem="(mem[0])}' >> memmetrics.txt & PID7=$!

# Get Swap metrics
cat /proc/meminfo | grep Swap | awk '{gsub( "[:':']","=" );print}' | awk 'BEGIN{i=0} {swap[i]=$2;i=i+1} END{print "SwapUsed="(swap[1]-swap[2])"\nSwapTotal="(swap[1])}' >> memmetrics.txt & PID8=$!

# Get Load Average metrics
cat /proc/loadavg | awk '{print "LoadAvg1="$1; print "LoadAvg5="$2; print "LoadAvg15="$3}' > loadavg.txt & PID9=$!

# Get Per-Interface Network metrics
rm networkinterfacemetrics.txt
OLD_IFS=$IFS
IFS=$'\n'
for nic in `grep : /proc/net/dev`
do 
    echo $nic | tr -d : >>/tmp/nicstats.txt
    echo $nic | tr -d : | \
    awk '{print "InOctets-"$1"="$2"\nOutOctets-"$1"="$10"\nInErrors-"$1"="$4"\nOutErrors-"$1"="$12"\nInDiscards-"$1"="$5"\nOutDiscards-"$1"="$13}' \
    >> networkinterfacemetrics.txt
done
IFS=$OLD_IFS

# Confirm completion of all processes
wait $PID1
wait $PID2
wait $PID3
wait $PID4
wait $PID5
wait $PID6
wait $PID7
wait $PID8
wait $PID9
