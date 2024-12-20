# event_push
This agent get events from Insightfinder edge cluster and sends it to Insightfinder main cluster.
## Installing the Agent

### Required Dependencies:
1. Python == 3.6.8
1. Pip3


### Docker
#### Create
Use the following command to create the docker image for this agent and push to our docker hub
```bash
docker build . -t insightfinderinc/event-push-agent:0.0.1
docker push insightfinderinc/event-push-agent:0.0.1
```
#### Run
Use the following commad to start the event push agent container

Current `conf.d` folder will be copied to the container automatically
```bash
docker run -itd --name if-event-push-agent -v ./conf.d:/opt/app-root/src/conf.d  docker.io/insightfinderinc/event-push-agent:0.0.1
```

#### Kubernetes
See [helm_chart/README.md](./helm_chart/README.md)

### Installation Steps:
1. Download the event_push.tar.gz package
1. Copy the agent package to the machine that will be running the agent
1. Extract the package
1. Navigate to the extracted location 
1. Configure venv and python dependencies
1. Configure agent settings under `conf.d/`
1. Test the agent
1. Run agent with cron.py

The final steps are described in more detail below. 

###### Configure venv and python dependencies:
The configure_python.sh script sets up a virtual python environment and installs all required libraries for running the agent. 

```bash
./setup/configure_python.sh
```

###### Agent configuration:
The config.ini file contains all of the configuration settings needed to connect to the Insightfinder edge cluster and to stream the data to Insightfinder main cluster.

```
python ./ifobfuscate.py 
```

The configure_python.sh script will generate a config.ini file for you; however, if you need to create a new one, you can simply copy the config.ini.template file over the config.ini file to start over. 

Populate all of the necessary fields in the config.ini file with the relevant data.  More details about each field can be found in the comments of the config.ini file and the Config Variables below. 

###### Test the agent:
Once you have finished configuring the config.ini file, you can test the agent to validate the settings. 

This will connect to the Insightfinder edge cluster, but it will not send any data to Insightfinder main cluster. This allows you to verify that you are getting data from Insightfinder edge cluster and that there are no failing exceptions in the agent configuration.

User `-p` to define max processes, use `--timeout` to define max timeout.

```bash
./setup/test_agent.sh
```

###### Run agent with cron:
For the agent to run continuously, it will need to run as a cron job with `cron.py`. 

```bash
nohup venv/bin/python3 cron.py &
```

###### Stopping the agent:
Once the cron is running, you can stop the agent by kill the `cron.py` process.

```bash
# get pid of backgroud jobs
jobs -l
# kill the cron process
kill -9 PID
```

###### Run agent with history data:
For the agent to replay history data, it may need to set `--timeout` with greater than 5 minutes.
 
Before run agent, please set `his_time_range` and `run_interval` in the config file. Please follow the description of these config vars. 

```bash
venv/bin/python3 event_push.py --timeout 60
```

###### Check the project info in edge cluster:
Agent support use command options to check the project info in edge cluster, please read help message to debug.

```bash
python3 event_push.py --help
``` 
 

### Config Variables
#### Insightfinder edge cluster
* **`if_url`**: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI.
* `retry`: Number of retry to send http requests. Default is `3`.
* `http_proxy`: HTTP proxy used to connect to InsightFinder.
* `https_proxy`: As above, but HTTPS.

#### Insightfinder main cluster
* **`if_url`**: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* **`user_name`**: User name in InsightFinder. Should be same as user name in edge cluster.
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI.
* `retry`: Number of retry to send http requests. Default is `3`.
* `http_proxy`: HTTP proxy used to connect to InsightFinder.
* `https_proxy`: As above, but HTTPS.

#### Runtime config
* `his_time_range`: History data time range, Example: 2020-04-14 00:00:00,2020-04-15 00:00:00. If this option is set, the agent will query results by time range.
* **`run_interval`**: How frequently (in Minutes) the agent is ran. For history data, this var is the time range of each api call, could set to 1440.


