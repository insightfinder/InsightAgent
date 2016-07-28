# InsightAgent: LogFileReplay
Agent Type: LogFileReplay

Platform: Linux

InsightAgent support replay mode of json log files in which the data from the json file is read and sent to insightfinder server.

##### Instructions to register a project in Insightfinder.com
- Go to the link https://insightfinder.com/
- Sign in with the user credentials or sign up for a new account.
- Go to Settings and Register for a project under "Insight Agent" tab.
- Give a project name, select Project Type as "Log File".
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
./deployment/checkpackages.sh
```
```
source pyenv/bin/activate
```
```
./deployment/install.sh -i PROJECT_NAME -u INSIGHTFINDER_USER_NAME -k LICENSE_KEY -s 0 -r 0 -t logFileReplay
```
3) Put data files in InsightAgent-master/data/
Make sure the contents of the file are in json format.

Example:
```
[
  {
    "eventId": 1000100001,
    "Root cause": "RC ID-00001\nMissing Feature"
  }
]
```
4) Run the following command for each data file.
```
python common/reportMetrics.py -m logFileReplay -f PATH_TO_JSON_FILE
```
Where PATH_TO_JSON_FILE is the path and filename of the json file.

After using the agent, use command "deactivate" to get out of python virtual environment.

