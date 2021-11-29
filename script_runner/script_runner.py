#!/usr/bin/python
import socket
import threading
import sys
import os
import subprocess
import time
import logging
import json
import requests
import shutil
import urllib3
from optparse import OptionParser
from shlex import quote

class ScriptFailWithCode(Exception):
    """Exception raised for script errors with an error code

    Attributes:
        error_code -- input salary which caused the error
        message -- error message
    """

    def __init__(self, code, message):
        self.code = code
        self.message = message

class ScriptFail(Exception):
    """Exception raised for failure without error code

    Attributes:
        message -- error message
    """

    def __init__(self, message):
        self.message = message

class ValidationFailed(Exception):
    """Exception raised for validating action request

    Attributes:
        message -- Validation failure message
    """

    def __init__(self, message):
        self.message = message


def getParameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run scripts from")
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="IF server to verify credentials")
    parser.add_option("-a", "--auditLog", 
                      action="store", dest="auditLog", help="Directory to store audit log")

    # Temporarily hardcoding to 4446 
    # parser.add_option("-p", "--port",
    #                  action="store", dest="listenPort", help="Port to listen for script requests")

    (options, args) = parser.parse_args()

    parameters = {}

    if options.homepath is None:
        parameters['homepath'] = os.getcwd()
    else:
        parameters['homepath'] = options.homepath
    
    if options.auditLog is None:
        parameters['auditLog'] = os.getcwd()
    else:
        parameters['auditLog'] = options.auditLog

    # Temporarily hardcoding to 4446 
    # if options.listenPort is None:
    #     parameters['listenPort'] = 4446
    # else:
    #     parameters['listenPort'] = options.listenPort
    
    parameters['listenPort'] = 4446

    if options.serverUrl is None:
        parameters['serverUrl'] = "https://stg.insightfinder.com"
    else:
        parameters['serverUrl'] = options.serverUrl

    return parameters


def verifyUser(username, licenseKey, projectName):
    alldata = {"userName": username, "operation": "verify", "licenseKey": licenseKey, "projectName": projectName}
    toSendDataJSON = json.dumps(alldata)
    url = parameters['serverUrl'] + "/api/v1/agentdatahelper"

    try:
        response = requests.post(url, data=json.loads(toSendDataJSON), verify=False)
    except requests.ConnectionError as e:
        logger.error("Connection failure : " + str(e))
        logger.error("Verification with InsightFinder credentials Failed")
        return False

    if response.status_code != 200:
        logger.error("Response from server: " + str(response.status_code))
        logger.error("Verification with InsightFinder credentials Failed")
        return False
    try:
        jsonResponse = response.json()
    except ValueError:
        logger.error("Not a valid response from server")
        logger.error("Verification with InsightFinder credentials Failed")
        return False

    return True

def sendFile(clientSocket, clientAddr, parameters):
    try: 
        request = clientSocket.recv(1024)
        audit.info("Client: {} Command: {}".format(clientAddr[0],str(request)))
        logger.debug("Request: " + str(request))
        request_parameters = json.loads(request.decode('utf-8'))
        project_name = request_parameters['p'].strip()
        user_name = request_parameters['u'].strip()
        license_key = request_parameters['lk'].strip()
        script_file = request_parameters['sf'].strip()
        script_command = request_parameters['sc'].strip()
        script_parameters = request_parameters['sp'].strip()
        affected_instance = None

        if verifyUser(user_name, license_key, project_name):
            ## Sanitize Inputs
            clean_cmd = shutil.which(script_command)

            if not clean_cmd:
                raise ValidationFailed("Invalid command: {}".format(script_command))

            if not script_file or not os.path.exists(os.path.join(parameters['homepath'], script_file)):
                raise ValidationFailed("Invalid script file: {}".format(script_file))
            
            valid_script = os.path.join(parameters['homepath'], script_file)

            if 'ain' in request_parameters.keys():
                affected_instance = request_parameters['ain'].strip()

            command = [clean_cmd, quote(valid_script)]

            if script_parameters:
                command.append(quote(script_parameters))
            
            if affected_instance: 
                command.append("--limit")
                command.append(quote(affected_instance))

            runCommand(command)
        else:
            raise ValidationFailed("Unverified User: {} ".format(user_name))
    except ValidationFailed as e: 
        logger.error(e)
        audit.info("Client: {} Action Status: Failed".format(clientAddr[0]))
        clientSocket.send("Status: 500".encode())
    except ScriptFail as e:
        logger.error(e)
        audit.info("Client: {} Action Status: Failed".format(clientAddr[0]))
        clientSocket.send("Status: 500".encode())
    except ScriptFailWithCode as e:
        logger.error(e)
        audit.info("Client: {} Action Status: Failed".format(clientAddr[0]))
        clientSocket.send("Status: 500".encode())
    else:
        audit.info("Client: {} Action Status: Success".format(clientAddr[0]))
        clientSocket.send("Status: 200".encode())
            
    clientSocket.close()


def runCommand(command):
    logger.debug(command)
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = proc.communicate()
    exit_code = proc.returncode
    logger.debug("Exit Code: {}".format(exit_code))
    logger.debug(out)
    if exit_code != 0:
        raise ScriptFailWithCode(exit_code, err)
    
    if "no hosts" in str(out.lower()) or len(str(out)) == 0 and ("failed" in str(err).lower() or "error" in str(err).lower() or "no such" in str(err).lower()):
        raise ScriptFail(err)


def acceptThread(parameters):
    acceptor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    acceptor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    acceptor.bind(('', int(parameters['listenPort'])))
    acceptor.listen(5)
    logger.info("Listening to connections on port " + str(parameters['listenPort']) + '\n')

    while True:
        (clientSock, clientAddr) = acceptor.accept()
        logger.info("==== Output Request =====")
        msg = "Connected to " + str(clientAddr[0]) + ":" + str(clientAddr[1])
        logger.info(msg)
        thread3 = threading.Thread(target=sendFile, args=(clientSock, clientAddr, parameters))
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


def setauditConfig(auditLog):
    # Set up the audit logger 
    ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
    logging_format = logging.Formatter(
        '{ts} [pid {pid}] {lvl} {msg}'.format(
            ts='%(asctime)s',
            pid='%(process)d',
            lvl='%(levelname)-8s',
            msg='%(message)s'),
        ISO8601[0])

    logger = logging.getLogger("auditlog")
    logger.setLevel(logging.INFO)

    logFile = os.path.join(auditLog, "audit.log")
    log_file = logging.FileHandler(logFile)

    log_file.setFormatter(logging_format)
    logger.addHandler(log_file)
    
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
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    logger = setloggerConfig()
    parameters = getParameters()
    audit = setauditConfig(parameters['auditLog'])
    main(parameters)
