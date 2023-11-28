#!/usr/bin/env python

import time, os, sys, shutil

def writetofile(filename,mysizeMB):
	# writes string to specified file repeatdely, until mysizeMB is reached. Then deletes file 
	mystring = "The quick brown fox jumps over the lazy dog"
	writeloops = int(1000000*mysizeMB/len(mystring))
	try:
		f = open(filename, 'w')
	except:
		# no better idea than:
		raise
	for x in range(0, writeloops):
		f.write(mystring)
	f.close()
	os.remove(filename)

def getCurrentDiskUsage(path):
  total, used, free = shutil.disk_usage(path)

  testWrite = (free*0.6)
  mysize = (testWrite // (2**30))*1024
  filename = os.path.join(path, 'outputTESTING.txt')
  writetofile(filename, mysize)

def help():
    print('This script writes to a file, consuming 60 percent of the total free space on the target path, then deletes the file. ')
    print('Required Argument:')
    print('--path <path>: The path where the file will be written.')
    sys.exit(1)

if __name__ == '__main__':
	path = None

	if len(sys.argv) != 3:
			help()

	for x in range(1, len(sys.argv), 2):
			arg = sys.argv[x]
			value = sys.argv[x+1]

			if arg == '--path' and not path:
					try: 
							path = str(value)
					except ValueError:
							help()
			else:
					help()
	print('Writing file to %s. Will delete following completion' % path)
	getCurrentDiskUsage(path)
	print('Finished')