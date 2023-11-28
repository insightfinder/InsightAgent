import time
import sys

units = {'KB': 1024, 'MB': 1024 * 1024, 'GB': 1024 * 1024 * 1024}
max_size = 2147483648 # 2GB - Limit for Legacy systems

def consume(size, unit, multiplier, duration, interval):
    string_size = size * units[unit]
    busy_string = string_size / interval

    if string_size > max_size:
        print('Exiting: String size over 2GB: %d bytes' % (string_size,))
        sys.exit(1)

    consumed = []

    for x in range(multiplier):
        consumed.append(' ' * int(busy_string))
    
    end = time.time() + float(duration)  # X minutes from now

    busy_time = duration / interval
    step_up = time.time() + float(busy_time)

    while True:
        
        if time.time() > step_up:
            step_up = time.time() + float(busy_time)
            for x in range(multiplier):
                consumed.append(' ' * int(busy_string))

        if time.time() > end:
            for x in consumed:
                del x
            break

def help():
    print('This script consumes system memory by allocating a configurable number of strings of configurable length for a configurable amount of time.')
    print('Required Arguments:')
    print('--size <integer>: Size of string to allocate, Capped at 2 GB to support older systems')
    print('--unit <KB,MB,GB>: Unit of measurment for string size')
    print('--multiplier <integer>: Number of strings to allocate')
    print('--duration <integer>: Duration of time in seconds to consume memory')
    print('--interval <integer>: Number of iterations that the memory will increase by. For Example: --interval 5 will make the memory increase 5 times over the duration.')
    sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) != 11:
        help()

    size = None
    unit = None
    multiplier = None
    duration = None
    interval = None

    for x in range(1, len(sys.argv), 2):
        arg = sys.argv[x]
        value = sys.argv[x+1]

        if arg == '--size' and not size:
            try: 
                size = int(value)
            except ValueError:
                help()
        elif arg == '--unit' and not unit:
            if value in units.keys():
                unit = value
            else:
                help()
        elif arg == '--multiplier' and not multiplier:
            try:
                multiplier = int(value)
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
 
    print('Consuming up to %d %s over the course of %d sec\n' % (size * multiplier, unit, duration))
    consume(size, unit, multiplier, duration, interval)
    print('Finished') 
