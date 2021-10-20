import sys
import time

pid = int(sys.argv[1])
timeout = int(sys.argv[2])
percent = int(sys.argv[3])

print('Starting Process: %d' % pid)

end = time.time() + float(timeout)  # X minutes from now
percentage = float(percent)/100
while time.time() < end:
    start = time.time()
    while time.time() - start < percentage:
        x = 1
    time.sleep(1-percentage)
    
print('Finished Process: %d' % pid)