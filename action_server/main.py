import configparser
import subprocess

import requests
import json
from datetime import datetime
from os import system

from app import ScriptFailWithCode


def readConfigFile(fileName):
    config = configparser.ConfigParser()
    config.read(fileName)
    return config

def writeConfigFile(serverid):
    config['DEFAULT']['serverid'] = str(serverid)
    config['DEFAULT']['reboot'] = str(datetime.now())
    with open('asconfig.ini', 'w') as configfile:
        config.write(configfile)

def verify():
    headers = {'content-type': 'application/json'}
    url = config['DEFAULT']['if_server_url'] + "/api/v2/IFActionServerServlet"
    cmdsJson = json.loads(config['DEFAULT']['cmds'])
    params = {'userName': config['DEFAULT']['username'], 'licenseKey': config['DEFAULT']['license'], 'projectName': config['DEFAULT']['project'],'instanceName': config['DEFAULT']['instancename'],
              'serverIp': config['DEFAULT']['serverip'], 'serverPort': config['DEFAULT']['serverport'], 'serverId': config['DEFAULT']['serverid'], 'cmds': json.dumps(list(cmdsJson.keys()))}
    response = requests.post(url, params=params, headers=headers)
    if response.status_code == 200:
        jsonData = json.loads(response.content)
        writeConfigFile(jsonData['serverid'])
    else:
        print(response.content)

def runCommand(command):
    result = subprocess.run(command, shell=True)
    if result.returncode != 0:
        raise ScriptFailWithCode(result.returncode)
        return make_response("failed to run command ", result.returncode)

if __name__ == '__main__':
    config = readConfigFile('asconfig.ini')
    verify()
    system("python3 -m flask run --cert=cert.pem --key=key.pem --host=0.0.0.0 --port=" + config['DEFAULT']['serverport'] + "&")