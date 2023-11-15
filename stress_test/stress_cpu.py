import os.path
import sys
from subprocess import Popen

python_cmd = "python2"

def consume(processes, percentage, duration, interval):
    if not os.path.exists("process.py"):
        print('Missing process.py library in local directory')
        sys.exit(1)
    
    count = 0
    process_list = []

    while count < processes:
        count += 1 
        process_list.append(Popen([python_cmd, "process.py", str(count), str(duration), str(percentage), str(interval)]))

    for process in process_list:
        process.wait()

def help():
    print('This script utilizes CPU cores at a configurable rate for a configurable amount of time.')
    print('Required Arguments:')
    print('--processes <integer>: Number of processes to run (Should be less than max system cores)')
    print('--percentage <integer>: Percentage of the CPU core to consume')
    print('--duration <integer>: Duration of time in seconds to consume CPU cores')
    print('--interval <integer>: Number of iterations to increase the cpu by. For example, entering "5" will increase the cpu usage 5 times over the duration until it reaches the designated percentage.')
    sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) != 9:
        help()

    processes = None
    percentage = None
    duration = None
    interval = None

    for x in range(1, len(sys.argv), 2):
        arg = sys.argv[x]
        value = sys.argv[x+1]

        if arg == '--processes' and not processes:
            try: 
                processes = int(value)
            except ValueError:
                help()
        elif arg == '--percentage' and not percentage:
            try:
                percentage = int(value)
            except ValueError:
                help()
        elif arg == '--duration' and not duration:
            try:
                duration = int(value)
            except ValueError:
                help()
        elif arg == '--interval' and not interval:
            try:
                interval = int(value)
            except ValueError:
                help()
        else:
            help()
 
    print ('utilizing %d cores, increasing usage %d times, up to %d percent, over the course of %d seconds\n' % (processes, interval, percentage, duration))
    consume(processes, percentage, duration, interval)
    print('Finished') 






