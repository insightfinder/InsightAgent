import os
import sys
import logging
from csv import reader
from pathlib import Path


def split_file(file_name, output='out'):
    with open(file_name) as json_data:
        logging.info(f"open {file_name}...")
        count = 0
        data = {}
        csv_reader = reader(json_data)
        header = next(csv_reader)  # skip header 

        for line in csv_reader:
            time_bucket, service_alias, client_alias, http_status, svc_mean, tx_mean, \
                req_count, value = line
            
            if service_alias not in data:
                data[service_alias] = ','.join(line)

            else:
                data[service_alias] += '\n' + ','.join(line)
            
    logging.info(f"found {len(data)} service alias")
    for key in data.keys():
        with open(os.path.join(output, key + '.csv'), 'a') as f:
            f.write(data[key])


def main():
    Path("out").mkdir(parents=True, exist_ok=True)
    for file_name in sys.argv[1:]:
        split_file(file_name, "out")
    

if __name__ == "__main__":
    main()

