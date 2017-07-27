#!/bin/sh
DATADIR='data/'
cd $DATADIR

dockers=$(docker ps --no-trunc -q)
for container in $dockers; do
    CONTAINER_PID=`docker inspect -f '{{ .State.Pid }}' $container`
    date +%s%3N | awk '{print "timestamp="$1}' > timestamp.txt & PID1=$!
    
    (cat /sys/fs/cgroup/memory/system.slice/docker-"$container".scope/memory.usage_in_bytes | awk '{print "MemUsed="$1}' > memmetrics_$container.txt ; 
    cat /sys/fs/cgroup/memory/system.slice/docker-"$container".scope/memory.limit_in_bytes | awk 'BEGIN{mem_total=0} {if($1<=999999999){mem_total+=$1}} END{print "MemTotal="mem_total}' >> memmetrics_$container.txt ;
    # Get Shared Memory metrics
    docker exec $container cat /proc/meminfo | grep Shmem | awk '{gsub( "[:':']","=" );print}' | awk 'BEGIN{mem[0]=0;i=0} {mem[i]=$2;i=i+1} END{print "SharedMem="(mem[0])}' >> memmetrics_$container.txt ;
    # Get Swap metrics
    docker exec $container cat /proc/meminfo | grep Swap | awk '{gsub( "[:':']","=" );print}' | awk 'BEGIN{swap[1]=0;i=0} {swap[i]=$2;i=i+1} END{print "SwapUsed="(swap[1]-swap[2])"\nSwapTotal="(swap[1])}' >> memmetrics_$container.txt) & PID2=$!
    
    cat /sys/fs/cgroup/blkio/system.slice/docker-"$container".scope/blkio.throttle.io_service_bytes | grep Read | awk 'BEGIN{readbytes=0} {if(NR==1){readbytes+=$3}} END{print "DiskRead="readbytes}' > diskmetricsread_$container.txt & PID3=$!
    cat /sys/fs/cgroup/blkio/system.slice/docker-"$container".scope/blkio.throttle.io_service_bytes | grep Write | awk 'BEGIN{writebytes=0} {if(NR==1){writebytes+=$3;}} END{print "DiskWrite="writebytes}' > diskmetricswrite_$container.txt & PID4=$!
    cat /proc/$CONTAINER_PID/net/dev | awk 'BEGIN{rxbytes=0;txbytes=0} {if(NR!=1 && NR!=2){if($1!="lo:"){rxbytes+=$2;txbytes+=$10;}}} END{print "NetworkIn="rxbytes; print "NetworkOut="txbytes}' > networkmetrics_$container.txt & PID5=$!
    cat /sys/fs/cgroup/cpuacct/system.slice/docker-"$container".scope/cpuacct.stat | awk 'BEGIN{cpu=0} {cpu+=$2} END{print "CPU="cpu}' > cpumetrics_$container.txt & PID6=$!

    # Get Filesystem metrics
    docker exec $container df -k | awk 'BEGIN{diskusedspace=0}{if(NR!=1)print "DiskUsed"$6"="$3; diskusedspace += $3}END{print "DiskUsed="diskusedspace}' > diskusedmetrics_$container.txt & PID7=$!

    # Get Per-Interface Network metrics
    rm networkinterfacemetrics_$container.txt
    while read -r line;
        do
            echo $line | tr -d : >>/tmp/nicstats_docker.txt
            echo $line | tr -d : | \
            awk '{print "InOctets-"$1"="$2"\nOutOctets-"$1"="$10"\nInErrors-"$1"="$4"\nOutErrors-"$1"="$12"\nInDiscards-"$1"="$5"\nOutDiscards-"$1"="$13}' \
            >> networkinterfacemetrics_$container.txt
        done << EOF
        $(grep : /proc/$CONTAINER_PID/net/dev)
EOF

    wait $PID1
    wait $PID2
    wait $PID3
    wait $PID4
    wait $PID5
    wait $PID6
    wait $PID7
done

