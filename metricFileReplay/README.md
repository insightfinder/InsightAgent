# InsightAgent: MetricFileReplay
Agent Type: MetricFileReplay

Platform: Linux

InsightAgent support replay mode of metric csv files in which the data from the csv file is read and sent to insightfinder server.

##### Instructions to register a project in Insightfinder.com
- Go to the link https://insightfinder.com/
- Sign in with the user credentials or sign up for a new account.
- Go to Settings and Register for a project under "Insight Agent" tab.
- Give a project name, select Project Type as "Metric File".
- Note down the project name and license key which will be used for agent installation. The license key is also available in "User Account Information". To go to "User Account Information", click the userid on the top right corner.

##### Pre-requisites:
Python 2.7.

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

# Steps to use replay mode:
1) Use the following command to download the insightfinder agent code.
```
wget --no-check-certificate https://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz
```
Untar using this command.
```
tar -xvf insightagent.tar.gz
```

2) In InsightAgent-master directory, run the following commands to install and use python virtual environment for insightfinder agent:
```
./deployment/checkpackages.sh -env
```
```
source pyenv/bin/activate
```
```
./deployment/install.sh -i PROJECT_NAME -u INSIGHTFINDER_USER_NAME -k LICENSE_KEY -s 1 -r 1 -t metricFileReplay
```
3) Put data files in InsightAgent-master/data/
Make sure each file is .csv formatted, starts with a row of headers and the headers should have "timestamp" field in it.

4) Run the following command for each data file.
```
pyenv/bin/python common/reportMetrics.py -m metricFileReplay -f PATH_TO_CSVFILENAME
```
Where PATH_TO_CSVFILENAME is the path and filename of the csv file.

After using the agent, use command "deactivate" to get out of python virtual environment.

