# stressTest

### stressTest Details
These scripts have been developed to stress the usage of a system. They have been built to minimize any external depencies to maintain support for legacy systems.

Currently, we have support for four metric stressors: 
1. CPU
2. Memory
3. Disk 
4. Network

To run these scripts, download the stressTest.tar.gz package and extract the scripts to a local directory on the target system. The required command line script arguments are documented below. 

Requirements:
Python 2.x, 3.x 

### CPU Stress Test
This script utilizes CPU cores at a configurable rate for a configurable amount of time. The script requires the utility script process.py to be in the local directory. 

Required Arguments:
* --processes <integer>: Number of processes to run (Should be less than max system cores)
* --percentage <integer>: Total Percentage of the CPU core to consume, including any other process running on the host.
* --duration <integer>: Duration of time in seconds to consume CPU cores
* --interval <integer>: Number of iterations to increase the CPU by. For example, entering "5" will increase the cpu usage in 5 iterations over the duration until it reaches the designated percentage.

Sample command: 
```
python stress_cpu.py --processes 4 --percentage 50 --duration 60 --interval 5
```
This command will increase the CPU usage to 50 percent on 4 cores over 60 seconds, increasing the usage by 10 percent every 12 seconds.

NOTE: The default configuration is to use python2; however, this can be changed via the `python_cmd` variable in the `stress_cpu.py` script. This variable will need to be updated from "python2" to "python3".

### Memory Stress Test
This script consumes system memory by allocating a configurable number of strings of configurable length for a configurable amount of time by increasing the memory to the point specified over a configurable number of iterations.

Required Arguments:
* --size <integer>: Size of string to allocate, Capped at 2 GB to support older systems
* --unit <KB,MB,GB>: Unit of measurment for string size
* --multiplier <integer>: Number of strings to allocate
* --duration <integer>: Duration of time in seconds to consume memory
* --interval <integer>: Number of iterations that the memory will increase by. For Example: --interval 5 will make the memory increase 5 times over the duration.

Sample command: 
```
python ./stress_memory.py --size 200 --unit MB --multiplier 10 --duration 60 --interval 5
```
This Command will increase the memory up to 2000 MB over the course of 60 seconds, increasing the memory used by 400 MB every 12 seconds. 


### Disk Stress Test
This script writes to a file, consuming 60% of the total free space on the target path, then deletes the file. 

NOTE: This script requires python3.x
NOTE: This script should be run as ROOT or as a user with ROOT level permissions

Required Arguments:
* --path <path>: The path where the file will be written.

Sample Command:
```
python3 stress_disk.py --path "/"
```
This will write the file to the root directory, stressing the default drive.

### Network Stress Test
This test uses the iperf utility. It requires two seperate systems to perform, both with iperf utility installed. 

On the test server:
  Install the iperf3 utility: 
    ```sudo yum install iperf3-3.1.7-2.el7.x86_64.rpm```
  Open firewall port 5102: 
    ```firewall-cmd --permanent --add-port=5201/udp```
    ```firewall-cmd --permanent --add-port=5201/tcp```
    ```firewall-cmd --reload```
  Start the iperf3 server
    ```iperf3 -s```

On a different server that can reach the test server
  Install the iperf3 utility: 
    ```sudo yum install iperf3-3.1.7-2.el7.x86_64.rpm```
  Run the iperf3 command
    ```iperf3 -c <IPADDRESS-OF-TEST-SERVER> -P 8 -t 30 -w 32768```
      -c 192.168.1.200 – IP address of the iPerf server
      -w 32768 – increase the TCP window size
      -t 30 – is the time in seconds for the test to be done (by default, it is 10 seconds)
      -P 8 – is the number of parallel threads (streams) to get the maximum channel load
