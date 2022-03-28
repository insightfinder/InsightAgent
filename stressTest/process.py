
import sys
import time

pid = int(sys.argv[1])
timeout = int(sys.argv[2]) #100
percent = int(sys.argv[3]) #50
interval = int(sys.argv[4]) #10

print('Starting Process: %d' % pid)

chunk = percent/interval #5
chunkTime = timeout/interval #10
increment = chunk

end = time.time() + float(timeout)  # X minutes from now

incrementTime = time.time() + float(chunkTime) #current time plus 10 seconds

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