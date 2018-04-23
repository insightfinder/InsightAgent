# InsightAgent: elasticsearch-logs
Agent Type: elasticsearch-logs

Platform: Linux

InsightFinder agent can be used to collect metrics from elasticsearch.

##### Instructions to register a project in Insightfinder.com
- Go to the link https://insightfinder.com/
- Sign in with the user credentials or sign up for a new account.
- Go to Settings and Register for a project under "Insight Agent" tab.
- Give a project name, select Project Type as "Private Cloud".
- Note down license key which is available in "User Account Information". To go to "User Account Information", click the userid on the top right corner.

##### Pre-requisites:
Elasticsearch should be installed and accessible on port 9200 (This can be changed via the [configuration file](#config) ).

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

3) Run the below command to install agent.The -w parameter can be used to give server url example ***-w http://192.168.78.85:8080***  in case you have an on-prem installation otherwise it is not required. The SAMPLING_INTERVAL  vaules support 10 second granularity along with minute granularity. Minute granularity can be set with a single integer whereas the 10 second granularity is set by using the value **10s**. e.g. **-s 10s**
```
./deployment/install.sh -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL -t AGENT_TYPE -w SERVER_URL
```


#### <a name="config"/>Configuration files</a>

1. ***elasticsearch-log/config.json***

   Use this file to configure the agent for your elasticsearch installation. The description of the different fields are:
    **"elasticsearchHost"** - Hostname of the elasticsearch installation
    **"elasticsearchPort"** - Port of the elasticsearch installation
    **"elasticsearchIndex"** - Index for the logs to send to InsightFinder
    **"timeFieldName"** - Field in elasticsearch documents containing timestamp/date
    **"isTimestamp"** - If log time field is datestring then **false** and if timestamp then **true**
    **"hostNameField"** - Field in elasticsearch documents containing hostname
    **"dateFormatInJodaTime"** - e.g "yyyy-MM-dd'T'HH:mm:ss",
    **"dateFormatInStrptime"** - e.g "%Y-%m-%dT%H:%M:%S",
    **"dataTimeZone"** - Timsezone of the logs e.g. Asia/Shanghai
    **"localTimeZone"** - Timsezone of the machine running the agent e.g. US/Eastern