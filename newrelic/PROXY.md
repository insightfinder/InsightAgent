# Proxy: newrelic
Agent Type: newrelic

Platform: Linux

InsightFinder agent can be used to monitor system performance metrics on bare metal machines or virtual machines.

##### Instructions to register a project in Insightfinder.com
- Go to [insightfinder.com](https://insightfinder.com/)
- Sign in with the user credentials or sign up for a new account.
- Go to Settings and Register for a project under "Datadog Agent" tab.
- Give a project name, select Project Type as "Private Cloud".
- View your account information by clicking on your user id at the top right corner of the webpage. Note the license key number.

##### Pre-requisites:
Python 2.7.

Python 2.7 must be installed in order to launch deployInsightAgent.sh. For Debian and Ubuntu, the following command will ensure that the required dependencies are present
```
sudo apt-get upgrade
sudo apt-get install build-essential libssl-dev libffi-dev python-dev wget
```
For Fedora and RHEL-derivatives
```
sudo yum update
sudo yum install gcc libffi-devel python-devel openssl-devel wget
```


##### To install agent on proxy server
1) Use the following command to download the insightfinder agent code.
```
wget --no-check-certificate https://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz
```
Untar using this command.
```
tar -xvf insightagent.tar.gz
```

Copy it to ```tomcat``` folder of the proxy server and rename folder to ```proxy```

2) run the following commands to install and use python virtual environment for insightfinder agent:
```
./deployment/checkpackages.sh
```
```
source pyenv/bin/activate
```

3) Run the below command to configure proxy for a user and his project.
```
./deployment/newrelic_install.sh -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE -p API_KEY
```
API_KEY can be obtained from datadog account on datadog website

After using the agent, use command "deactivate" to get out of python virtual environment.

4) To delete project configuration for the user and project run

```
./deployment/undeploy.sh -i PROJECT_NAME -u USER_NAME 
```
It will clear all cron jobs, data for the project


