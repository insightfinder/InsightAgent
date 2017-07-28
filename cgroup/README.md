# InsightAgent: cgroup
Agent Type: cgroup

Platform: Linux

InsightFinder agent can be used to monitor system metrics of docker containers using cgroup.

Tested with Ubuntu 14.04, Redhat 6.8, Redhat 7.2, Centos 7.1, Amazon Linux AMI 2016.03.3.

Required docker version: 1.9.1 and later.

##### Instructions to register a project in Insightfinder.com
- Go to [insightfinder.com](https://insightfinder.com/)
- Sign in with the user credentials or sign up for a new account.
- Go to Settings and Register for a project under "Insight Agent" tab.
- Give a project name, select Project Type as "Private Cloud".
- View your account information by clicking on your user id at the top right corner of the webpage. Note the license key number.

##### Pre-requisites:
Python 2.7.

Python 2.7 must be installed in order to launch deployInsightAgent.sh. For Debian and Ubuntu, the following command will ensure that the required dependencies are present
```
sudo apt-get update
sudo apt-get install build-essential libssl-dev libffi-dev python-dev
```
For Fedora and RHEL-derivatives
```
sudo yum update
sudo yum install gcc libffi-devel python-devel openssl-devel
```

##### To deploy agent on multiple hosts

- Get the deployment script from GitHub using below command
```
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployment/deployInsightAgent.sh
```
and change the permissions with the command
```
 chmod 755 deployInsightAgent.sh
```
-Ensure all machines have the same login username and password.
-Obtain the IP address for every machine (or host) the InsightFinder agent will be installed on.
-Include the IP address of all hosts in hostlist.txt, entering one IP address per line.
-To deploy run the following command
```
./deployInsightAgent.sh -n USER_NAME_IN_HOST
                        -i PROJECT_NAME_IN_INSIGHTFINDER
                        -u USER_NAME_IN_INSIGHTFINDER
                        -k LICENSE_KEY
                        -s SAMPLING_INTERVAL_MINUTE
                        -r REPORTING_INTERVAL_MINUTE
                        -t AGENT_TYPE
AGENT_TYPE is *cgroup*.
```
##### To view command in terminal, run
```
./deployInsightAgent.sh
```
To validate deployment, select to enter either a password or key. For a key, enter the identity file's path name. For example: /home/insight/.ssh/id_rsa


##### To undo agent deployment on multiple hosts
- Get the script for stopping agents from GitHub with the following command
```
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployment/stopcron.sh
```
and change the permissions with the command
```
 chmod 755 stopcron.sh
```
- Include IP address of all hosts in hostlist.txt and enter one IP address per line.
- To stop the agent run the following command
```
./stopcron.sh -n USER_NAME_IN_HOST -p PASSWORD

USER_NAME_IN_HOST - username used to login into the host machines
PASSWORD - password or name of the identity file along with path
```

##### To install agent on local machine:
1) Use the following command to download the insightfinder agent code.
```
wget --no-check-certificate https://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz
```
Untar using this command.
```
tar -xvf insightagent.tar.gz
```

2) In InsightAgent-master directory, run the following commands to install dependencies for insightfinder agent (If -env flag is used then a seperate virtual environment is created):
```
sudo ./deployment/checkpackages.sh  
OR
./deployment/checkpackages.sh -env
```

3) Run the below command to install agent.(The -w parameter can be used to give server url example ***-w http://192.168.78.85:8080***  in case you have an on-prem installation otherwise it is not required)
```
./deployment/install.sh -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE -w SERVER_URL
```

##### To check raw data in host machines
- Login into the individual host machines
- In the InsightAgent-master/data folder, all raw data will be stored in csv files. csv files older than 5 days are moved to /tmp folder.
- To change the retention period, edit the InsightAgent-master/reporting_config.json and change the "keep_file_days" to the required value.

