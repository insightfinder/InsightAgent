#!/bin/sh
DATADIR='data/'
cd $DATADIR

dockers=$(docker ps --no-trunc | awk '{if(NR!=1)print $1}')
for container in $dockers; do
    CONTAINER_PID=`docker inspect -f '{{ .State.Pid }}' $container`
    date +%s%3N | awk '{print "timestamp="$1}' > timestamp.txt & PID1=$!
    cat /sys/fs/cgroup/memory/docker/$container/memory.usage_in_bytes | awk '{print "MemUsed="$1}' > memmetrics_$container.txt & PID2=$!
    cat /sys/fs/cgroup/blkio/docker/$container/blkio.throttle.io_service_bytes | grep Read | awk 'BEGIN{readbytes=0} {if(NR!=1){readbytes+=$3}} END{print "DiskRead="readbytes}' > diskmetricsread_$container.txt & PID3=$!
    cat /sys/fs/cgroup/blkio/docker/$container/blkio.throttle.io_service_bytes | grep Write | awk 'BEGIN{writebytes=0} {if(NR!=1){writebytes+=$3;}} END{print "DiskWrite="writebytes}' > diskmetricswrite_$container.txt & PID4=$!
    cat /proc/$CONTAINER_PID/net/dev | awk 'BEGIN{rxbytes=0;txbytes=0} {if(NR!=1 && NR!=2){if($1!="lo:"){rxbytes+=$2;txbytes+=$10;}}} END{print "NetworkIn="rxbytes; print "NetworkOut="txbytes}' > networkmetrics_$container.txt & PID5=$!
    cat /sys/fs/cgroup/cpuacct/docker/$container/cpuacct.stat | awk 'BEGIN{cpu=0} {cpu+=$2} END{print "CPU="cpu}' > cpumetrics_$container.txt & PID6=$!

    wait $PID1
    wait $PID2
    wait $PID3
    wait $PID4
    wait $PID5
    wait $PID6
done

