
import sys
import time

pid = int(sys.argv[1])
timeout = int(sys.argv[2])
percent = int(sys.argv[3])
interval = int(sys.argv[4])

print('Starting Process: %d' % pid)

chunk = percent/interval
chunkTime = timeout/interval
increment = chunk

end = time.time() + float(timeout)

incrementTime = time.time() + float(chunkTime)

while time.time() < end:
    busyPercent = float(increment)/100
    if time.time() >= incrementTime:
        incrementTime = time.time() + float(chunkTime)
        increment += chunk
    start = time.time()
    while time.time() - start < busyPercent:
        x = 1
    time.sleep(1-busyPercent)
    
print('Finished Process: %d' % pid)