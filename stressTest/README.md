# stressTest

### stressTest Details
These scripts have been developed to stress the usage of a system. They have been built to minimize any external depencies to maintain support for legacy systems.

Currently, we have support for two metric stressors: 
1. CPU
1. Memory 

To run these scripts, download the stressTest.tar.gz package and extract the scripts to a local directory on the target system. The required command line script arguments are documented below. 

Requirements:
Python 2.x, 3.x 

### CPU Stress Test
This script utilizes CPU cores at a configurable rate for a configurable amount of time to be increased up to the rate over a configurable amount of iterations. The script requires the utility script process.py to be in the local directory. 

Required Arguments:
* --processes <integer>: Number of processes to run (Should be less than max system cores)
* --percentage <integer>: Percentage of the CPU core to consume
* --duration <integer>: Duration of time in seconds to consume CPU cores
* --interval <integer>: Number of iterations to increase the CPU by. For example, entering "5" will increase the cpu usage 5 times over the duration until it reaches the designated percentage.

Sample command: 
```
python stress_cpu.py --process 4 --percentage 50 --duration 60 --interval 5
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
