# event_push
This agent get events from Insightfinder edge cluster and sends it to Insightfinder main cluster.
## Installing the Agent

### Required Dependencies:
1. Python 3.x 
1. Pip3

###### Installation Steps:
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

### Config Variables
#### Insightfinder edge cluster
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. 
* **`project_name`**: Name of the project created in the InsightFinder UI. 
* **`project_type`**: Type of the project - one of `metric, metricreplay, log, logreplay, incident, incidentreplay, alert, alertreplay, deployment, deploymentreplay`.
* `timezone`: Timezone for selected user. Default is `UTC`.
* **`if_url`**: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `retry`: Number of retry to send http requests. Default is `3`.
* `http_proxy`: HTTP proxy used to connect to InsightFinder.
* `https_proxy`: As above, but HTTPS.

#### Insightfinder main cluster
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. 
* **`project_name`**: Name of the project created in the InsightFinder UI, If this project is not exist, agent will create it automatically.
* `system_name`: Name of system owned by project. If project_name is not exist in InsightFinder, agent will create a new system automatically from this field or project_name. 
* **`project_type`**: Type of the project - one of `metric, metricreplay, log, logreplay, alert, alertreplay, incident, incidentreplay, deployment, deploymentreplay, trace, tracereplay`.
* `containerize`: Set to `YES` if project is container.
* **`sampling_interval`**: How frequently (in Minutes) data is collected. Should match the interval used in project settings. 
* **`if_url`**: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `retry`: Number of retry to send http requests. Default is `3`.
* `http_proxy`: HTTP proxy used to connect to InsightFinder.
* `https_proxy`: As above, but HTTPS.

#### Runtime config
* **`run_interval`**: How frequently (in Minutes) the agent is ran.
* **`query_timewindow_of_multiple_run_interval`**: The time window of the requested data, in multiples of run_interval. Default is 3.


