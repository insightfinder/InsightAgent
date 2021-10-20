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
This script utilizes CPU cores at a configurable rate for a configurable amount of time. The script requires the utility script process.py to be in the local directory. 

Required Arguments:
* --processes <integer>: Number of processes to run (Should be less than max system cores)
* --percentage <integer>: Percentage of the CPU core to consume
* --duration <integer>: Duration of time in seconds to consume CPU cores

Sample command: 
```
python stress_cpu.py --process 4 --percentage 50 --duration 60
```

NOTE: The default configuration is to use python2; however, this can be changed via the `python_cmd` variable in the `stress_cpu.py` script. This variable will need to be updated from "python2" to "python3".

### Memory Stress Test
This script consumes system memory by allocating a configurable number of strings of configurable length for a configurable amount of time.

Required Arguments:
* --size <integer>: Size of string to allocate, Capped at 2 GB to support older systems
* --unit <KB,MB,GB>: Unit of measurment for string size
* --multiplier <integer>: Number of strings to allocate
* --duration <integer>: Duration of time in seconds to consume memory

Sample command: 
```
python ./stress_memory.py --size 200 --unit MB --multiplier 10 --duration 60
```
