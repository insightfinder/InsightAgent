import configparser
import logging
import subprocess
import sys
from os import system
from flask import Flask, make_response, request

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

def runCommand(command):
    logger.debug(command)
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = proc.communicate()
    exit_code = proc.returncode
    logger.debug("Exit Code: {}".format(exit_code))
    logger.debug(out)
    if exit_code != 0:
        raise ScriptFailWithCode(exit_code, err)
        return make_response("failed to run command ", exit_code)
    if "no hosts" in str(out.lower()) or len(str(out)) == 0 and (
            "failed" in str(err).lower() or "error" in str(err).lower() or "no such" in str(err).lower()):
        raise ScriptFail(err)
        return make_response("failed to run command " + err, 422)
    return make_response("Success ", 200)

class LessThanFilter(logging.Filter):
    def __init__(self, exclusive_maximum, name=""):
        super(LessThanFilter, self).__init__(name)
        self.max_level = exclusive_maximum

    def filter(self, record):
        # non-zero return means we log this message
        return 1 if record.levelno < self.max_level else 0
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

app = Flask(__name__)
config = configparser.ConfigParser()
config.read("asconfig.ini")
logger = setloggerConfig()

@app.route('/run', methods=['POST'])
def hello_post():
    serverId = request.form.get('serverId')
    if (serverId == config['DEFAULT']['serverid']):
        cmd = request.form.get('cmd')
        return runCommand(cmd)
    else:
        msg = f'Fail!'
        return make_response(msg, 422)
