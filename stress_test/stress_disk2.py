#!/usr/bin/env python

import time
import os
import sys
import shutil

def write_chunk_to_file(file, chunk_size, remaining_size):
    mystring = "The quick brown fox jumps over the lazy dog"
    writeloops = min(chunk_size // len(mystring), remaining_size // len(mystring))
    # print(writeloops)

    try:
        with open(file, 'a') as f:
            for x in range(writeloops):
                f.write(mystring)
    except Exception as e:
            print("Error opening the file:", e)
            sys.exit(1)

def write_to_file_over_time(filename, target_size, chunk_size, duration_seconds, ratio):
    # try:
    #     f = open(filename, 'w')
    # except Exception as e:
    #     print("Error opening the file:", e)
    #     sys.exit(1)

    start_time = time.time()
    current_size = 0

    sleep_time = duration_seconds / ratio
    print("target size:", target_size, ratio, duration_seconds, sleep_time)

    while current_size < target_size:
        remaining_size = target_size - current_size
        print("bytes written:", current_size, "remaining_size:", remaining_size, "chunk_size:", chunk_size)
        write_chunk_to_file(filename, chunk_size, remaining_size)
        current_size += chunk_size

        # elapsed_time = time.time() - start_time
        # time_left = max(duration_seconds - elapsed_time, 0)
        # print("current_size =", current_size, ", time_left =", time_left)

        # Sleep for the remaining time to make the writes happen over the specified duration
        time.sleep(sleep_time)

def getCurrentDiskUsage(path):
    total, used, free = shutil.disk_usage(path)

    final_needed = int(total * 0.90)  # Adjust the percentage of free space you want to consume
    write_size = int(final_needed - used)
    filename = os.path.join(path, 'outputTESTING.txt')
    chunk_size = 50 * 1024 * 1024 # in bytes
    ratio = write_size // chunk_size
    duration_seconds = 90 * 60

    # Write over a period of 10 minutes, using chunks of 10 MB at a time
    write_to_file_over_time(filename, write_size, chunk_size, duration_seconds, ratio)

def help():
    print('This script writes to a file, consuming 80 percent of the total free space on the target path, then deletes the file.')
    print('Required Argument:')
    print('--path <path>: The path where the file will be written.')
    sys.exit(1)

if __name__ == '__main__':
    path = None

    if len(sys.argv) != 3:
        help()

    for x in range(1, len(sys.argv), 2):
        arg = sys.argv[x]
        value = sys.argv[x + 1]

        if arg == '--path' and not path:
            try:
                path = str(value)
            except ValueError:
                help()
        else:
            help()

    print('Writing file to %s over a period of 10 minutes.' % path)
    getCurrentDiskUsage(path)
    print('Finished')
