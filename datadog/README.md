# InsightAgent: datadog
Agent Type: datadog

Platform: Linux

InsightFinder agent can be used to monitor system performance metrics on bare metal machines or virtual machines.

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
sudo apt-get upgrade
sudo apt-get install build-essential libssl-dev libffi-dev python-dev wget
```
For Fedora and RHEL-derivatives
```
sudo yum update
sudo yum install gcc libffi-devel python-devel openssl-devel wget
```

##### To install agent on the machine
1) Use the following command to download the insightfinder agent code.
```
wget --no-check-certificate https://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz
```
Untar using this command.
```
tar -xvf insightagent.tar.gz
```

2) run the following commands to install and use python virtual environment for insightfinder agent:
```
./deployment/checkpackages.sh -env
```
```
source pyenv/bin/activate
```

For offline installation of packages do:
```
tar xvf InsightAgent-master/deployment/DeployAgent/files/pip_packages.tar.gz
sudo pip install --no-index --find-links='pip_packages' datadog requests
```

5) Run the below command to install agent.(The -w parameter can be used to give server url example ***-w http://192.168.78.85:8080***  in case you have an on-prem installation otherwise it is not required)
```
./deployment/install.sh -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -t datadog -w SERVER_URL
```
After using the agent, use command "deactivate" to get out of python virtual environment.

6) In InsightAgent-master directory, make changes to the config file.
```
datadog/config.ini
```
Update the app_key and api_key. These keys can be obtained by clicking on Integrations >  API tab > Create keys on datadog website.
