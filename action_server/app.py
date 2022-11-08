import configparser
import json
import logging
import subprocess
import sys
import ssl
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
    result = subprocess.run(command, shell=True)
    if result.returncode != 0:
        raise ScriptFailWithCode(result.returncode, "failed to run script")
        return make_response("failed to run command ", result.returncode)
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
cmdsJson = json.loads(config['DEFAULT']['cmds'])
logger = setloggerConfig()

@app.route('/run', methods=['Get'])
def hello_get():
    return "hello"

@app.route('/run', methods=['POST'])
def hello_post():
    serverId = request.form.get('serverId')
    if serverId == config['DEFAULT']['serverid']:
        cmd = request.form.get('cmd')
        if cmdsJson[cmd]:
            isTargetAll = request.form.get('isTargetAll')
            instance = request.form.get('instance')
            if instance:
                return runCommand(cmdsJson[cmd] + " --limit " + instance)
            else:
                return runCommand(cmdsJson[cmd])
        else:
            msg = f'CMD not in whitelist!'
            return make_response(msg, 422)
    else:
        msg = f'Fail!'
        return make_response(msg, 422)

if __name__ == "__main__":
    context = ssl.create_default_context()
    context.check_hostname = False
    ciphers = (
        'ECDH+AESGCM:DH+AESGCM:ECDH+AES256:DH+AES256:ECDH+AES128:DH+AES:ECDH+HIGH:'
        'DH+HIGH:ECDH+3DES:DH+3DES:RSA+AESGCM:RSA+AES:RSA+HIGH:RSA+3DES:ECDH+RC4:'
        'DH+RC4:RSA+RC4:!aNULL:!eNULL:!MD5'
    )
    context.set_ciphers(ciphers)
    context.load_cert_chain('cert.pem', 'key.pem')
    app.run(ssl_context=context)
