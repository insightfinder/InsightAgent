# extrahop
This agent collects data from extrahop and sends it to Insightfinder.
## Installing the Agent

### Required Dependencies:
1. Python == 3.6.8
1. Pip3

###### Installation Steps:
1. Download the extrahop.tar.gz package
1. Copy the agent package to the machine that will be running the agent
1. Extract the package
1. Navigate to the extracted location 
1. Configure venv and python dependencies
1. Configure agent settings under `conf.d/`
1. Test the agent
1. Run agent with cron.py

The final steps are described in more detail below. 

###### Install freetds for linux/osx before install agent
```bash
osx: brew install freetds
linux: yum install freetds
```

###### Configure venv and python dependencies:
The configure_python.sh script sets up a virtual python environment and installs all required libraries for running the agent. 

```bash
./setup/configure_python.sh
```

###### Agent configuration:
The config.ini file contains all of the configuration settings needed to connect to the extrahop and to stream the data to Insightfinder cluster.

```
python ./ifobfuscate.py 
```

The configure_python.sh script will generate a config.ini file for you; however, if you need to create a new one, you can simply copy the config.ini.template file over the config.ini file to start over. 

Populate all of the necessary fields in the config.ini file with the relevant data.  More details about each field can be found in the comments of the config.ini file and the Config Variables below. 

###### Test the agent:
Once you have finished configuring the config.ini file, you can test the agent to validate the settings. 

This will connect to the extrahop, but it will not send any data to Insightfinder cluster. This allows you to verify that you are getting data from Insightfinder edge cluster and that there are no failing exceptions in the agent configuration.

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
* **`host`**: Extrahop's host info.
* **`api_key`**: Extrahop's api_key info.
* **`object_type`**: This dield is used for query metrics, only support "device" for now.
* `device_ip_list`: Device ip list. Multiple ips split with ','. If this options is empty, all active devices will be used.
* **`metric_query_params`**: Metrics query params, support multiple metric category.
* `his_time_range`: History data time range, Example: 2020-04-14 00:00:00,2020-04-15 00:00:00. If this option is set, the agent will query metric values by time range.
* **`data_format`**: The format of the data to parse: RAW, RAWTAIL, CSV, CSVTAIL, XLS, XLSX, JSON, JSONTAIL, AVRO, or XML. \*TAIL formats keep track of the current file being read & the position in the file.
* `timestamp_format`: Format of the timestamp, in python [arrow](https://arrow.readthedocs.io/en/latest/#supported-tokens). If the timestamp is in Unix epoch, this can be set to `epoch`. If the timestamp is split over multiple fields, curlies can be used to indicate formatting, ie: `YYYY-MM-DD HH:mm:ss ZZ`; alternatively, if the timestamp can be in one of multiple fields, a priority list of field names can be given: `timestamp1,timestamp2`.
* `timezone`: Timezone of the timestamp data stored in/returned by the DB. Note that if timezone information is not included in the data returned by the DB, then this field has to be specified. 
* **`timestamp_field`**: Field name for the timestamp. Default is `time`.
* `target_timestamp_timezone`: Timezone of the timestamp data to be sent and stored in InsightFinder. Default value is UTC. Only if you wish to store data with a time zone other than UTC, this field should be specified to be the desired time zone.
* `component_field`: Field name for the component name.
* `instance_field`: Field name for the instance name. Default is the device id(oid).
* `instance_whitelist`: This field is a regex string used to define which instances will be filtered.
* `device_field`: Field name for the device/container for containerized projects. This can also use a priority list, field names can be given: `device1,device2`.
* `thread_pool`: Number of thread to used in the pool, default is 20.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. 
* `token`: Token from your Account Profile in the InsightFinder UI. 
* **`project_name`**: Name of the project created in the InsightFinder UI, If this project is not exist, agent will create it automatically.
* `system_name`: Name of system owned by project. If project_name is not exist in InsightFinder, agent will create a new system automatically from this field or project_name. 
* **`project_type`**: Type of the project - one of `metric, metricreplay, log, logreplay, incident, incidentreplay, alert, alertreplay, deployment, deploymentreplay`.
* `containerize`: Set to `YES` if project is container.
* **`sampling_interval`**: How frequently (in Minutes) data is collected. Should match the interval used in project settings.
* **`run_interval`**: How frequently (in Minutes) the agent is ran. Should match the interval used in cron.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.



