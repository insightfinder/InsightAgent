# InsightAgent: Docker Remote Api
Agent Type: docker_remote_api

Platform: Linux

Tested on Redhat 7.2.

Required docker version: 1.9.1 and later.

InsightFinder agent can be used to monitor system metrics of docker containers using docker remote api.

##### Instructions to register a project in Insightfinder.com
- Go to the link https://insightfinder.com/
- Sign in with the user credentials or sign up for a new account.
- Go to Settings and Register for a project under "Insight Agent" tab.
- Give a project name, select Project Type as "Private Cloud".
- Note down license key which is available in "User Account Information". To go to "User Account Information", click the userid on the top right corner.

##### Pre-requisites:
Minimum required docker version for monitoring docker containers: v1.7.x
Python 2.7.

This pre-requisite is needed on the machine which launches deployInsightAgent.py.
For Debian and Ubuntu, the following command will ensure that the required dependencies are installed:
```
sudo apt-get upgrade
sudo apt-get install build-essential libssl-dev libffi-dev python-dev wget
```
For Fedora and RHEL-derivatives, the following command will ensure that the required dependencies are installed:
```
sudo yum update
sudo yum install gcc libffi-devel python-devel openssl-devel wget
```

##### To deploy agent on multiple hosts:

- Get the deployment script from github using below command:
```
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployment/deployInsightAgent.py
```
- Get IP address of the hosts on which docker containers are running.
- All machines should have same login username and password.
- Include IP address of all hosts in hostlist.txt and enter one IP address per line.
- To deploy run the following command:
```
./deployInsightAgent.sh -n USER_NAME_IN_HOST
                        -i PROJECT_NAME_IN_INSIGHTFINDER
                        -u USER_NAME_IN_INSIGHTFINDER
                        -k LICENSE_KEY
                        -s SAMPLING_INTERVAL_MINUTE
                        -r REPORTING_INTERVAL_MINUTE
                        -t AGENT_TYPE
AGENT_TYPE is *docker_remote_api*.
```
- When the above script is run, if prompted for password, enter either the password or the name of the identity file along with file path.
Example: /home/insight/.ssh/id_rsa


##### To get more details on the command, run
```
./deployInsightAgent.sh
```

##### To undo agent deployment on multiple hosts:
- Get the script for stopping agents from github using below command:
```
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployment/stopcron.py
```

- Include IP address of all hosts in hostlist.txt and enter one IP address per line.
- To stop the agent run the following command:
```
python stopcron.py -n USER_NAME_IN_HOST -p PASSWORD

USER_NAME_IN_HOST - username used to login into the host machines
PASSWORD - password or name of the identity file along with path
```

##### To install agent on local machine:
```
./deployment/install.sh -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE
```

##### To check raw data in host machines:
- Login into the individual host machines.
- In the InsightAgent-master/data folder, all raw data will be stored in csv files. csv files older than 5 days are moved to /tmp folder.
- To change the retention period, edit the InsightAgent-master/reporting_config.json and change the "keep_file_days" to the required value.
