# InsightAgent: Docker remote api
Agent Type: docker_remote_api

Platform: Linux

InsightFinder agent can be used to monitor performance metrics of docker containers using docker remote api.

###### Pre-requisites:
This pre-requisite is needed on the machine which launches deployInsightAgent.py.
For Debian and Ubuntu, the following command will ensure that the required dependencies are installed:

sudo apt-get install build-essential libssl-dev libffi-dev python-dev

For Fedora and RHEL-derivatives, the following command will ensure that the required dependencies are installed:

sudo yum install gcc libffi-devel python-devel openssl-devel

###### To deploy agent on multiple hosts:

- Get the deployment script from github using below command:
```
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployInsightAgent.py
```
- Get IP address of the hosts on which docker containers are running.
- All machines should have same login username and password.
- Include IP address of all hosts in hostlist.txt and enter one IP address per line.
- To deploy run the following command:
```
python deployInsightAgent.py -n USER_NAME_IN_HOST
                             -u USER_NAME_IN_INSIGHTFINDER 
                             -k LICENSE_KEY 
                             -s SAMPLING_INTERVAL_MINUTE 
                             -r REPORTING_INTERVAL_MINUTE 
                             -t AGENT_TYPE
```
AGENT_TYPE is *docker_remote_api*.

When the above script is run, if prompted for password, enter either the password or the name of the identity file along with file path.
Example: /home/insight/.ssh/id_rsa


###### To get more details on the command, run 
```
python deployInsightAgent.py -h
```

###### To undo agent deployment on multiple hosts:
- Get the script for stopping agents from github using below command:
```
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/stopcron.py
```

- Include IP address of all hosts in hostlist.txt and enter one IP address per line.

- To stop the agent run the following command:
```
python stopcron.py -n USER_NAME_IN_HOST -p PASSWORD
```

###### To install agent on local machine:
```
./install.sh -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE
```


