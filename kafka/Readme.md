# InsightAgent: Kafka
Agent Type: Kafka

Platform: Linux

InsightFinder agent can be used to collect metrics from kafka.

##### Instructions to register a project in Insightfinder.com
- Go to the link https://insightfinder.com/
- Sign in with the user credentials or sign up for a new account.
- Go to Settings and Register for a project under "Insight Agent" tab.
- Give a project name, select Project Type as "Private Cloud".
- Note down license key which is available in "User Account Information". To go to "User Account Information", click the userid on the top right corner.

##### Pre-requisites:
Kafka should be installed and accessible on port 9092 (This can be changed via the [configuration file](#config) ). The topic name the agent consumes from is ***"insightfinder_csv"***. Another file is ***"header.txt"*** which contains the fields which are being reported through the data in kafka. Its format is:
<pre>
Metric Name1, Group ID1
Metric Name2, Group ID2
</pre>

This pre-requisite is needed on the machine which launches deployInsightAgent.sh.
For Debian and Ubuntu, the following command will ensure that the required dependencies are installed:
``` linux
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
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployment/deployInsightAgent.sh
```
- Change permission of "deployInsightAgent.sh" as a executable.
- Get IP address of all machines (or hosts) on which InsightFinder agent needs to be installed.
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
AGENT_TYPE is *kafka*.
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
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployment/stopcron.sh
```
nd change the permissions with the command.
```
 chmod 755 stopcron.sh
```
- Include IP address of all hosts in hostlist.txt and enter one IP address per line.
- To stop the agent run the following command:

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

2) In InsightAgent-master directory, run the following commands to install and use python virtual environment for insightfinder agent:
```
./deployment/checkpackages.sh
```
```
source pyenv/bin/activate
```

3) Run the below command to install agent.
```
./deployment/install.sh -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE
```
After using the agent, use command "deactivate" to get out of python virtual environment.


#### <a name="config"/>Configuration files</a>

1. ***data/config.txt***

   Create file in the "data" directory with the following format for changing the default values of the mentioned parameters:
<pre>
hostname
port
topic
</pre>
   If you need to just change a specific parameter just leave the other lines blank. Default values for the parameters are:

    * hostname - localhost
    * port - 9092
    * topic - insightfinder_csv

2. ***data/hostname.txt***

  File contains the hostname of the file whose metrics are being collected. If not present defaults to the hostname of the local machine.
