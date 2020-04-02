# coding=utf-8
import os
import regex
import glob
import commands
from optparse import OptionParser
from csvsort import csvsort

UNDERSCORE = regex.compile(r"\_+")
PERIOD = regex.compile(r"\.")


def handle_same_format_files(file_paths, out_file_path):
    # get file lines
    count = -1
    for count, line in enumerate(open(str(file_paths[0]), 'rU')):
        pass
    print 'Rows: {}'.format(count)

    print "Start to merge file {}".format(out_file_path)
    # open files
    file_list = [open(str(fp), "rb") for fp in file_paths]
    file_names = map(lambda a: os.path.basename(a.name), file_list)

    if os.path.exists(out_file_path):
        os.remove(out_file_path)
    fout = open(str(out_file_path), "a")

    # combine headers
    new_headers = []
    header_cols = []
    for index, item in enumerate(file_list):
        file_name = file_names[index]
        metric = os.path.splitext(file_name)[0]
        if '|' not in metric:
            metric = PERIOD.sub('_', UNDERSCORE.sub('', metric))
        else:
            metric = metric.partition('|')
            metric = PERIOD.sub('_', UNDERSCORE.sub('', '{}.{}'.format(
                '.'.join(metric[2].split('.')[1:]), metric[0])))

        header = item.readline().replace('\r', '').replace('\n', '')
        header_cols = map(lambda a: a.replace('"', ''), header.split(',"')[1:])
        for col in header_cols:
            new_headers.append(col + ',metric:' + metric)
    new_headers_str = ',' + ','.join(['"' + item + '"' for item in new_headers]) + '\n'
    fout.write(new_headers_str)
    print "Metric files: {}, Instances: {}".format(len(file_list), len(header_cols))
    print "All columns: {}".format(len(new_headers) + 1)

    # combine data
    num = 0
    while num < count:
        data_list_all = [item.readline().replace('\r', '').replace('\n', '').split(',') for item in file_list]
        data_list = reduce(lambda x, y: x + y[1:], data_list_all)
        data_str = ','.join(data_list) + '\n'

        fout.write(data_str)
        num += 1
        if num % 10000 == 0:
            fout.flush()
            print "Complete {} rows".format(num)
    print "Complete {} rows".format(num)

    # close files
    fout.close()
    for item in file_list:
        item.close()


def handle_diff_format_files(file_paths, out_file_path, step, memory):
    merged_file_name = os.path.dirname(out_file_path) + '/_merged_file.csv'
    sorted_file_name = os.path.dirname(out_file_path) + '/_sorted_file.csv'

    if not step or step == '1':
        print "Start to merge file {}".format(merged_file_name)
        # open files
        file_list = [open(str(fp), "rb") for fp in file_paths]
        file_names = map(lambda a: os.path.basename(a.name), file_list)
        file_header_points = []
        file_header_cols = []

        # merge metric files
        if os.path.exists(merged_file_name):
            os.remove(merged_file_name)
        fout = open(str(merged_file_name), "a")
        # combine headers
        new_headers = []
        header_lens = 0
        for index, item in enumerate(file_list):
            file_name = file_names[index]
            metric = os.path.splitext(file_name)[0]
            if '|' not in metric:
                metric = PERIOD.sub('_', UNDERSCORE.sub('', metric))
            else:
                metric = metric.partition('|')
                metric = PERIOD.sub('_', UNDERSCORE.sub('', '{}.{}'.format(
                    '.'.join(metric[2].split('.')[1:]), metric[0])))

            header = item.readline().replace('\r', '').replace('\n', '')
            header_cols = map(lambda a: a.replace('"', ''), header.split(',"')[1:])
            # set the header cols points
            file_header_points.append(header_lens)
            file_header_cols.append(header_cols)
            header_lens += len(header_cols)

            for col in header_cols:
                new_headers.append(col + ',metric:' + metric)
        new_headers_str = ',' + ','.join(['"' + item + '"' for item in new_headers]) + '\n'
        fout.write(new_headers_str)
        print "Metric files: {}".format(len(file_list))
        print "All columns: {}".format(len(new_headers) + 1)

        # combine data
        num = 0
        for index, item in enumerate(file_list):
            header_points = file_header_points[index]
            header_cols = file_header_cols[index]
            pre_cols = ['' for i in range(0, header_points)]
            post_cols = ['' for i in range(0, header_lens - header_points - len(header_cols))]
            for line in item:
                cols = line.replace('\r', '').replace('\n', '').split(',')
                time_cols = cols[:1]
                data_cols = cols[1:]
                new_cols = time_cols + pre_cols + data_cols + post_cols
                data_str = ','.join(new_cols) + '\n'

                if len(new_cols) != len(new_headers) + 1:
                    print "Error merge row {}".format(num)
                    continue

                fout.write(data_str)
                num += 1
                if num % 10000 == 0:
                    fout.flush()
                    print "Complete {} rows".format(num)
        print "Complete {} rows".format(num)

        # close files
        fout.close()
        for item in file_list:
            item.close()
        print "Merged file {}".format(merged_file_name)

    if not step or step == '2':
        # sort the big merged metric file by timestamp
        print "Start to sort file {}".format(sorted_file_name)
        if os.path.exists(sorted_file_name):
            os.remove(sorted_file_name)

        # use csv sort lib
        # csvsort(merged_file_name, [0], output_filename=sorted_file_name, max_size=int(memory), has_header=True,
        #         delimiter=',', show_progress=True)
        # print "Sorted file {}".format(sorted_file_name)

        # use GNU sort
        command_sort = "sort -t , -k 1,1n -S {} -o {} {}".format(memory, sorted_file_name, merged_file_name)
        (status, output) = commands.getstatusoutput(command_sort)
        if status == 0:
            print "Sorted file {}".format(sorted_file_name)
        else:
            print "Fail sorted file {}".format(sorted_file_name)

    if not step or step == '3':
        print "Start to combine file {}".format(out_file_path)
        if os.path.exists(out_file_path):
            os.remove(out_file_path)
        fout = open(str(out_file_path), "a")
        with open(str(sorted_file_name), "rb") as sorted_file:
            same_timestamp = None
            same_timestamp_rows = []
            same_timestamp_data_map = {}

            num = -1
            row_num = 0
            for line in sorted_file:
                num += 1
                if num == 0:
                    # write header
                    fout.write(line)
                else:
                    # write data
                    cols = line.replace('\r', '').replace('\n', '').split(',')
                    timestamp = cols[0]
                    data_cols = cols[1:]

                    if num == 1:
                        same_timestamp = timestamp
                        same_timestamp_rows = [data_cols]
                    else:
                        if timestamp == same_timestamp:
                            same_timestamp_rows.append(data_cols)
                        else:
                            # combine rows
                            parse_combine_data(fout, same_timestamp, same_timestamp_rows, same_timestamp_data_map)
                            row_num += 1
                            if row_num % 10000 == 0:
                                fout.flush()
                                print "Complete {} rows".format(row_num)

                            # reset timestamp and data
                            same_timestamp = timestamp
                            same_timestamp_rows = [data_cols]
                            same_timestamp_data_map = {}

            if same_timestamp and len(same_timestamp_rows) > 0:
                # combine rows
                parse_combine_data(fout, same_timestamp, same_timestamp_rows, same_timestamp_data_map)
                row_num += 1

            print "Complete {} rows".format(row_num)

        # close files
        fout.close()
        print "Combine file {}".format(out_file_path)


def parse_combine_data(fout, same_timestamp, same_timestamp_rows, same_timestamp_data_map):
    new_data_cols = []
    for row in same_timestamp_rows:
        for index, col in enumerate(row):
            same_timestamp_data_map[index] = same_timestamp_data_map.get(index) or col
    for key, value in same_timestamp_data_map.items():
        new_data_cols.append(value)

    new_cols = [same_timestamp] + new_data_cols
    data_str = ','.join(new_cols) + '\n'

    fout.write(data_str)


def main():
    """
    Example：python2 merge_csv_files.py -f same -m 1G -i "./*.csv" -o ./output.csv
    """
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-f", "--flag",
                      action="store", dest="flag")
    parser.add_option("-s", "--step",
                      action="store", dest="step")
    parser.add_option("-m", "--memory",
                      action="store", dest="memory", help="Max memory used.")
    parser.add_option("-i", "--infiles",
                      action="store", dest="in_file_path", help="Files to process.")
    parser.add_option("-o", "--outfile",
                      action="store", dest="out_file_path", help="File to save.")

    (options, args) = parser.parse_args()

    flag = options.flag
    step = options.step
    memory = options.memory
    in_file_path = options.in_file_path
    out_file_path = options.out_file_path
    if flag is None:
        flag = 'diff'
    if memory is None:
        memory = '1G'
    if in_file_path is None:
        in_file_path = "/Users/zhangzinan/Downloads/dd-test/*.csv"
    if out_file_path is None:
        out_file_path = "/Users/zhangzinan/Downloads/dd-test-out/all_metrics.csv"

    file_paths = glob.glob(in_file_path)
    if len(file_paths) == 0:
        return
    print 'Input file path: ' + in_file_path

    if flag == 'same':
        handle_same_format_files(file_paths, out_file_path)
    elif flag == 'diff':
        handle_diff_format_files(file_paths, out_file_path, step, memory)

    print "\nFinished"


if __name__ == '__main__':
    main()
