# InsightAgent: LogFileReplay
Agent Type: LogFileReplay

Platform: Linux

InsightAgent support replay mode of json log files in which the data from the json file is read and sent to insightfinder server. A sample log file is as follows:

```json
[{"eventId": 1480750759682, "data": " INFO org.apache.hadoop.hdfs.server.namenode.TransferFsImage: Downloaded file fsimage.ckpt_0000000000000000020 size 120 bytes.\n"}, {"eventId": 1480750759725, "Data": " INFO org.apache.hadoop.hdfs.server.namenode.NNStorageRetentionManager: Going to retain 2 images with txid >= 18\n"}, {"eventId": 1480754359850, "Data": " INFO org.apache.hadoop.hdfs.server.namenode.FSNamesystem: Roll Edit Log from 127.0.0.1\n"}]
```

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
sudo apt-get -E upgrade
sudo apt-get -E install build-essential libssl-dev libffi-dev python-dev wget
```
For Fedora and RHEL-derivatives, the following command will ensure that the required dependencies are installed:
```
sudo -E yum update
sudo -E yum install gcc libffi-devel python-devel openssl-devel wget
```

# Steps to use replay mode:
1) Use the following command to download the insightfinder agent code.
```
wget --no-check-certificate https://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz
or
wget --no-check-certificate http://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz
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
./deployment/install.sh -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL -t logFileReplay -w SERVER_URL
```
The -w parameter can be used to give server url example ***-w http://192.168.78.85:8080***  in case you have an on-prem installation otherwise it is not required.

3) Run the following command for each data file.
```
python common/reportMetrics.py -m logFileReplay -f PATH_TO_JSON_FILE
```
Where PATH_TO_JSON_FILE is the path and filename of the json file.
Note: If running from a different server, add the -w SERVER_NAME option.

After using the agent, use command "deactivate" to get out of python virtual environment.
