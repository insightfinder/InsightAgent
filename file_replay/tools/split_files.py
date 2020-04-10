# coding=utf-8
import os
from optparse import OptionParser

import arrow

# read cache, set 500M if has 16G MEM
FILE_READ_CHUNK_SIZE = 500 * 1024 * 1024


def mkdir(path):
    folder = os.path.exists(path)
    if not folder:
        os.makedirs(path)


def handle_csv_filter(in_file_path, time_range):
    in_dir = os.path.dirname(in_file_path)

    range_list = time_range.split(';')
    timestamp_range = []
    last_time = 0
    for time_range_str in range_list:
        range_list = time_range_str.split(',')
        time_start = arrow.get(range_list[0], 'YYYY-MM-DD HH:mm:ss').timestamp
        time_end = arrow.get(range_list[1], 'YYYY-MM-DD HH:mm:ss').timestamp
        timestamp_range.append([time_start, time_end])
        last_time = time_end
    timestamp_range.reverse()

    out_path = os.path.join(in_dir, 'time_filter.csv')
    output_file = open(str(out_path), "a")
    num = 0
    filter_num = 0
    [time_start, time_end] = timestamp_range.pop()
    with open(str(in_file_path), "rb") as _file:
        output_header = _file.readline()
        output_file.write(output_header)
        num += 1
        buf_lines = _file.readlines(FILE_READ_CHUNK_SIZE)
        while buf_lines:

            for line in buf_lines:
                timestamp = int(line[:10])

                if time_start <= timestamp <= time_end:
                    output_file.write(line)

                    filter_num += 1
                    if filter_num % 1000 == 0:
                        output_file.flush()
                        print "Complete {} rows".format(filter_num)

                elif timestamp > last_time:
                    print "Complete {} rows".format(filter_num)
                    return

                elif timestamp > time_end and len(timestamp_range) > 0:
                    [time_start, time_end] = timestamp_range.pop()

                num += 1
                if num % 1000 == 0:
                    output_file.flush()
                    print "Read {} rows".format(num)

            buf_lines = _file.readlines(FILE_READ_CHUNK_SIZE)


def handle_csv_split(in_file_path):
    in_dir = os.path.dirname(in_file_path)

    output_header = None
    file_day = None
    output_file = None
    num = 0
    with open(str(in_file_path), "rb") as _file:
        output_header = _file.readline()
        num += 1
        buf_lines = _file.readlines(FILE_READ_CHUNK_SIZE)
        while buf_lines:

            for line in buf_lines:
                timestamp = line[:10]
                day = arrow.get(int(timestamp)).format('YYYY-MM-DD')

                if day != file_day:
                    file_day = day
                    folder = os.path.join(in_dir, 'output-' + file_day)
                    file_name = file_day + '.csv'
                    if output_file:
                        print 'Output is done'
                        output_file.close()

                    mkdir(folder)

                    print 'Output start to write: ' + file_name
                    out_path = os.path.join(folder, file_name)
                    output_file = open(str(out_path), "a")
                    output_file.write(output_header)
                    output_file.write(line)

                else:
                    output_file.write(line)

                num += 1
                if num % 1000 == 0:
                    output_file.flush()
                    print "Complete {} rows".format(num)

            buf_lines = _file.readlines(FILE_READ_CHUNK_SIZE)

    print "Complete {} rows".format(num)


def main():
    """
    Example：python2 split_files.py  -i "test.csv" -t "2018-10-03 22:50:00,2018-10-03 23:59:00"
    """
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-i", "--infile",
                      action="store", dest="in_file_path", help="File to split.")
    parser.add_option("-t", "--time_range",
                      action="store", dest="time_range", help="Time range to filter.")

    (options, args) = parser.parse_args()

    in_file_path = options.in_file_path
    time_range = options.time_range
    if in_file_path is None:
        in_file_path = "test.csv"

    print 'Input file path: ' + in_file_path

    if time_range:
        handle_csv_filter(in_file_path, time_range)
    else:
        handle_csv_split(in_file_path)

    print "\nFinished"


if __name__ == '__main__':
    main()
