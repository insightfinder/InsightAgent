import os
import sys
import logging
from csv import reader
from pathlib import Path
import time

from multiprocessing import Process, Queue

def split_file(file_name, q):
    with open(file_name) as json_data:
        logging.info(f"open {file_name}...")
        csv_reader = reader(json_data)
        header = next(csv_reader)  # skip header 

        for line in csv_reader:
            time_bucket, service_alias, client_alias, http_status, svc_mean, tx_mean, \
                req_count, value = line

            # put line in queue
            q.put([service_alias, ','.join(line)])

        print("done split file")
            

def write_file(q, i):
    # print(f"writer {i}")
    while True:
        try:
            key, line = q.get(timeout=5)
            # print(f"writer {i} got {line[:40]}")
            with open(os.path.join("out", key + '.csv'), 'a+') as f:
                f.write(line+"\n")
            # sleep(5)
        except Exception as e:
            print(e)
            break


def main():
    q = Queue()
    Path("out").mkdir(parents=True, exist_ok=True)
    
   # start data processing
    splitters = []
    for file_name in sys.argv[2:]:
        p = Process(target=split_file,
                    args=(file_name, q)
                    )
        splitters.append(p)


    for p in splitters:
        p.start()

    writers = []
    for i in range(int(sys.argv[1])):
        p = Process(target=write_file,
                    args=(q, i)
                    )
        writers.append(p)

    for p in writers:
        p.start()


    for p in splitters:
        p.join()

    for p in writers:
        p.join()

    print("complete")

if __name__ == "__main__":
    start = time.time()
    main()
    print(time.time()-start)

