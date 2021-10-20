import os.path
import sys
from subprocess import Popen

python_cmd = "python2"

def consume(processes, percentage, duration):
    if not os.path.exists("process.py"):
        print('Missing process.py library in local directory')
        sys.exit(1)
    
    count = 0
    process_list = []

    while count < processes:
        count += 1 
        process_list.append(Popen([python_cmd, "process.py", str(count), str(duration), str(percentage)]))

    for process in process_list:
        process.wait()

def help():
    print('This script utilizes CPU cores at a configurable rate for a configurable amount of time.')
    print('Required Arguments:')
    print('--processes <integer>: Number of processes to run (Should be less than max system cores)')
    print('--percentage <integer>: Percentage of the CPU core to consume')
    print('--duration <integer>: Duration of time in seconds to consume CPU cores')
    sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) != 7:
        help()

    processes = None
    percentage = None
    duration = None

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
        else:
            help()
 
    print ('utilizing %d cores for %d sec at %d percent\n' % (processes, duration, percentage))
    consume(processes, percentage, duration)
    print('Finished') 






