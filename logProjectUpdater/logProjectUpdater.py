import requests
import json
import sys
import urllib3
from configparser import ConfigParser
import os

list_api = "/api/v1/loadProjectsInfo"

TOKEN = "token"
USER_AGENT = "User-Agent"
X_CSRF_TOKEN = "X-CSRF-Token"

def log_in(host, user_name, password, user_agent):
    url = host + '/api/v1/login-check'
    headers = {"User-Agent": user_agent}
    data = {"userName": user_name, "password": password}
    
    try: 
        resp = requests.post(url, data=data, headers=headers, verify=False)

        if resp.status_code == 200:
            headers = {USER_AGENT: user_agent, X_CSRF_TOKEN: json.loads(resp.text)[TOKEN]}
        else: 
            sys.exit("Login Failed: Status Code: %d" % resp.status_code)

    except requests.exceptions.RequestException as e:  
        sys.exit(e)

    return resp.cookies, headers

def get_config_vars():
    try:
        if os.path.exists(os.path.join(os.getcwd(), "config.ini")):
            parser = ConfigParser()
            parser.read(os.path.join(os.getcwd(), "config.ini"))
            url = parser.get('Insightfinder', 'url')
            login_user = parser.get('Insightfinder', 'login_user')
            login_pass = (parser.get('Insightfinder', 'login_pass'))
            similarity_degree = parser.get('Sensitivity', 'similarity_degree')
            sensitivity = parser.get('Sensitivity', 'sensitivity')
            update_sensitivity = parser.get('Sensitivity', 'update_sensitivity')
            keywords = (parser.get('Keywords', 'keywords'))
            update_keywords = parser.get('Keywords', 'update_keywords')

            if len(url) == 0:
                print("Agent not correctly configured(url). Check config file.")
                sys.exit(1)
            if len(login_user) == 0:
                print("Agent not correctly configured(login_user). Check config file.")
                sys.exit(1)
            if len(login_pass) == 0:
                print("Agent not correctly configured(login_pass). Check config file.")
                sys.exit(1)
            if len(similarity_degree) == 0:
                print("Agent not correctly configured(login_pass). Check config file.")
                sys.exit(1)
            if len(sensitivity) == 0:
                print("Agent not correctly configured(login_pass). Check config file.")
                sys.exit(1)
            if len(keywords) == 0:
                print("Agent not correctly configured(login_pass). Check config file.")
                sys.exit(1)    
            if len(update_sensitivity) == 0:
                print("Agent not correctly configured(login_pass). Check config file.")
                sys.exit(1)    
            if len(update_keywords) == 0:
                print("Agent not correctly configured(login_pass). Check config file.")
                sys.exit(1)    

    except IOError:
        print("config.ini file is missing")

    config_vars = {
        'url': url,
        'login_user': login_user,
        'login_pass': login_pass,
        'sensitivity': sensitivity,
        'similarity_degree': similarity_degree,
        'keywords': keywords,
        'update_keywords': update_keywords,
        'update_sensitivity': update_sensitivity
    }
    return config_vars

def update_log_project_settings(projects, config_vars):
  updated = 0 

  for project in projects['data']['basicProjectData']:
    if projects['data']['basicProjectData'][project]['dataType'] == 'Log':
      resp = requests.post(("%s/api/v1/projects/update?project=%s&pvalue=%s&similaritySensitivity=%s&rareEventAlertThresholds=1&operation=updateprojsettings" % (url, project, config_vars['sensitivity'], config_vars['similarity_degree'])), headers=headers, cookies=cookies, verify=False)
      if resp.status_code != 200:
        print("Project update error: {}".format(project))
      else: 
        updated += 1


  print("Updated {} log projects".format(updated))

def update_keywords(projects, config_vars):
    updated = 0

    for project in projects['data']['basicProjectData']:
        if projects['data']['basicProjectData'][project]['dataType'] == 'Log':
            resp = requests.post(("%s/api/v1/projectkeywords?projectName=%s&type=whitelist&keywords=[%s]"% (url, project,config_vars['keywords'])), headers=headers, cookies=cookies, verify=False)
            if resp.status_code != 200:
                print("Project update error: {}".format(project))
            else: 
                updated += 1

    print("Updated {} projects keywords".format(updated))

if __name__ == "__main__":
  urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

  config_vars = get_config_vars()

  url = config_vars['url']
  user = config_vars['login_user']
  password = config_vars['login_pass']

  user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.122 Safari/537.36"
  (cookies, headers) = log_in(url, user, password, user_agent)

  resp = requests.get(url + list_api, headers=headers, cookies=cookies, verify=False)

  projects = json.loads(resp.text)
  
  if(config_vars['update_sensitivity'] == 'true'):
    update_log_project_settings(projects, config_vars)
  if(config_vars['update_keywords'] == 'true'):
    update_keywords(projects, config_vars)
