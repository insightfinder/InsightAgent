#!/bin/sh
DATADIR='data/'
cd $DATADIR

for SEARCHKEY in "rubis_apache" "rubis_db"
do
apacheweb=$(docker ps --no-trunc | grep $SEARCHKEY | awk '{print $1}')
if [ -z "$apacheweb" ]
then
continue
else
echo $apacheweb
CONTAINER_PID=`docker inspect -f '{{ .State.Pid }}' $apacheweb`
date +%s%3N | awk '{print "timestamp="$1}' > timestamp.txt & PID1=$!
cat /cgroup/memory/docker/$apacheweb/memory.usage_in_bytes | awk '{print "MemUsed="$1}' > memmetrics_$SEARCHKEY.txt & PID2=$!

cat /cgroup/blkio/docker/$apacheweb/blkio.throttle.io_service_bytes | grep Read | awk '{if(NR!=1){readbytes+=$3}} END{print "DiskRead="readbytes}' > diskmetricsread_$SEARCHKEY.txt & PID3=$!
cat /cgroup/blkio/docker/$apacheweb/blkio.throttle.io_service_bytes | grep Write | awk '{if(NR!=1){writebytes+=$3;}} END{print "DiskWrite="writebytes}' > diskmetricswrite_$SEARCHKEY.txt & PID4=$!
cat /proc/$CONTAINER_PID/net/dev | awk '{if(NR!=1 && NR!=2){if($1!="lo:"){rxbytes+=$2;txbytes+=$10;}}} END{print "NetworkIn="rxbytes; print "NetworkOut="txbytes}' > networkmetrics_$SEARCHKEY.txt & PID5=$!
cat /cgroup/cpuacct/docker/$apacheweb/cpuacct.stat | awk '{cpu+=$2} END{print "CPU="cpu}' > cpumetrics_$SEARCHKEY.txt & PID6=$!

wait $PID1
wait $PID2
wait $PID3
wait $PID4
wait $PID5
wait $PID6
fi
done
