#!/usr/bin/python
import socket
import threading
import sys
import os
import shlex
import subprocess
import time
from optparse import OptionParser
import logging


def getParameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-p", "--port",
                      action="store", dest="listenPort", help="Directory to run from")
    (options, args) = parser.parse_args()

    parameters = {}
    if options.homepath is None:
        parameters['homepath'] = os.getcwd()
    else:
        parameters['homepath'] = options.homepath
    if options.listenPort is None:
        parameters['listenPort'] = 4445
    else:
        parameters['listenPort'] = options.listenPort
    return parameters


def checkPrivilege():
    euid = os.geteuid()
    if euid != 0:
        args = ['sudo', sys.executable] + sys.argv + [os.environ]
        os.execlpe('sudo', *args)


class prepareThreads(threading.Thread):
    def __init__(self, command, path):
        super(prepareThreads, self).__init__()
        self.command = command
        self.path = path

    def run(self):
        proc = subprocess.Popen(self.command, cwd=self.path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (out, err) = proc.communicate()
        if "failed" in str(err) or "ERROR" in str(err):
            logger.error("Task failed.")
            sys.exit()
        logger.info(out)


def sendFile(self, parameters):
    request = self.recv(1024)
    logger.debug("Request: " + str(request))
    requestParts = shlex.split(request)
    msgType = requestParts[0]
    if msgType != "GET":
        return
    command = parameters['homepath'] + "/script_runner/clean_disk.sh"
    logger.debug(command)
    thread = prepareThreads(command, parameters['homepath'])
    thread.start()
    thread.join()


def acceptThread(parameters):
    acceptor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    acceptor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    acceptor.bind(('', int(parameters['listenPort'])))
    acceptor.listen(5)
    cur_thread = threading.current_thread()
    logger.info("Listening to connections on port " + str(parameters['listenPort']) + '\n')

    while True:
        (clientSock, clientAddr) = acceptor.accept()
        print "==== Output Request ====="
        msg = "Connected to " + str(clientAddr[0]) + ":" + str(clientAddr[1])
        logger.info(msg)
        thread3 = threading.Thread(target=sendFile(clientSock, parameters))
        thread3.daemon = True
        thread3.start()
    acceptor.close()
    return


def setloggerConfig():
    # Get the root logger
    logger = logging.getLogger(__name__)
    # Have to set the root logger level, it defaults to logging.WARNING
    logger.setLevel(logging.INFO)
    # route INFO and DEBUG logging to stdout from stderr
    logging_handler_out = logging.StreamHandler(sys.stdout)
    logging_handler_out.setLevel(logging.DEBUG)
    logging_handler_out.addFilter(LessThanFilter(logging.WARNING))
    logger.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logger.addHandler(logging_handler_err)
    return logger


class LessThanFilter(logging.Filter):
    def __init__(self, exclusive_maximum, name=""):
        super(LessThanFilter, self).__init__(name)
        self.max_level = exclusive_maximum

    def filter(self, record):
        # non-zero return means we log this message
        return 1 if record.levelno < self.max_level else 0


def main(parameters):
    listenThread = threading.Thread(target=acceptThread, args=(parameters,))
    listenThread.daemon = True
    listenThread.start()
    try:
        while 1:
            time.sleep(.1)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    # checkPrivilege()
    logger = setloggerConfig()
    parameters = getParameters()
    main(parameters)
