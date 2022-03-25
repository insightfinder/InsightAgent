
import sys
import time

pid = int(sys.argv[1])
timeout = int(sys.argv[2]) #100
percent = int(sys.argv[3]) #50
interval = int(sys.argv[4]) #10

print('Starting Process: %d' % pid)

chunk = percent/interval #5
chunkTime = timeout/interval #10
increment = 0

end = time.time() + float(timeout)  # X minutes from now
percentage = float(percent)/100
incrementTime = time.time() + float(chunkTime) #current time plus 10 seconds
while time.time() < end:
    incrementPercent = float(increment)/100
    if time.time() >= incrementTime:
        incrementTime = time.time() + float(chunkTime)
        increment += chunk
    start = time.time()
    while time.time() - start < percentage:
        x = 1
    time.sleep(1-incrementPercent)
    print(incrementPercent)
    
print('Finished Process: %d' % pid)