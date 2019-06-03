# InsightAgent: newrelic
Agent Type: newrelic

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

3) Run the below command to install agent.(The -w parameter can be used to give server url example ***-w http://192.168.78.85:8080***  in case you have an on-prem installation otherwise it is not required)
```
./deployment/install.sh -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -r REPORTING_INTERVAL -t newrelic -w SERVER_URL -s SAMPLING_INTERVAL
REPORTING_INTERVAL is the time interval for backend collectior
SAMPLING_INTERVAL is the time interval for data sampling interval
```
After using the agent, use command "deactivate" to get out of python virtual environment.

4) In InsightAgent-master directory, make changes to the config file.
```
newrelic/config.ini
```
```
[newrelic]
api_key = 
# applications to include (default all)
app_name_filter = 
# hosts to include (default all)
host_filter = 
# mectrics to include (default all)
# this should be formatted as metric_name:value|value,metric_name:value|value
metrics = CPU/User Time:percent,Memory/Heap/Used:used_mb_by_host,Memory/Physical:used_mb_by_host,Instance/connectsReqPerMin:requests_per_minute,Controller/reports/show:average_response_time|calls_per_minute|call_count|min_response_time|max_response_time|average_exclusive_time|average_value|total_call_time_per_minute|requests_per_minute|standard_deviation|throughput|average_call_time|min_call_time|max_call_time|total_call_time
# how frequently (in min) to run this agent (must change value here and in /etc/cron.d/ifagent)
run_interval = 
agent_http_proxy = 
agent_https_proxy = 

[insightfinder]
user_name = 
license_key = 
project_name = 
sampling_interval = 
# what size to limit chunks sent to IF to, as kb
chunk_size_kb = 1024
url = https://app.insightfinder.com
if_http_proxy = 
if_https_proxy = 
```