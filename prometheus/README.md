# Prometheus
This agent collects data from prometheus and sends it to Insightfinder.
## Installing the Agent

### Required Dependencies:
1. Python 3.x 
1. Pip3

###### Installation Steps (On prem / local installation):
1. Download the prometheus.tar.gz package
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
The config.ini file contains all of the configuration settings needed to connect to the Prometheus instance and to stream the data to InsightFinder.

The password for the Prometheus user will need to be obfuscated using the ifobfuscate.py script.  It will prompt you for the password and provide the value to add to the configuration file. 

```
python ./ifobfuscate.py 
```

The configure_python.sh script will generate a config.ini file for you; however, if you need to create a new one, you can simply copy the config.ini.template file over the config.ini file to start over. 

Populate all of the necessary fields in the config.ini file with the relevant data.  More details about each field can be found in the comments of the config.ini file and the Config Variables below.

If you want create a container project, please set variable `containerize=yes`, and set variable `device_field` to specify field name of container.

###### Test the agent:
Once you have finished configuring the config.ini file, you can test the agent to validate the settings. 

This will connect to the Prometheus instance, but it will not send any data to InsightFinder. This allows you to verify that you are getting data from Prometheus and that there are no failing exceptions in the agent configuration.

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
# get pid of background jobs
jobs -l
# kill the cron process
kill -9 PID
``` 

### Config Variables
**Prometheus Settings**
* **`prometheus_uri`**: URI for Prometheus API as `scheme://host:port` (Required)
  * Defaults to `http://localhost:9090`
* **`user`**: User name of Basic Authentication. (Required)
* **`password`**: Password of Basic Authentication. (Required)
* **`verify_certs`**: True or False if certificates should be verified. (Optional)
* **`ca_certs`**: Path to CA bundle. (Optional)
* **`client_cert`**: Path to certificate file. (Optional)
* **`client_key`**: Path to client key file. (Optional)
* **`prometheus_query`**: Prometheus query used to query all needed metrics. (Optional)
  * If not set, it will use `{__name__=~".+"}` to query all metrics
  * Example: `{instance="$instance-name",__name__=~"$regex-for-metrics"}`
  * Leave Blank if providing **`prometheus_query_json`** file
* **`prometheus_query_metric_batch_size`**: If prometheus_query is set, this is the batch size of metrics to query in one request. (Optional)
  * Keep it empty if you want to query all metrics in one request
* **`batch_metric_filter_regex`**: Regex to filter metrics if batch size is set (Optional)
* **`prometheus_query_json`**: The json file containing the prometheus query. (Optional)
  * Leave blank if providing **`prometheus_query`**
  * For each json object, it contains "query", optional "metric_batch_size", optional "metric_name" and optional "instance_fields" string array.
  * Example: prometheus_query_json = prometheus_query.json
* **`metrics_name_field`**: This field is used to get metric's name from response data field. (Optional)
  * Multiple fields are separated by commas. 
  * Example: `__name__, job`, the `metric name` =  `{__name__}_{job}`
  * If nothing specified, agent will use the metric name from config var `metrics`.
* **`his_time_range`**: Historical data time range. (Optional)
  * If this option is set, the agent will query metric values by time range.
  * Example: 2020-04-14 00:00:00,2020-04-15 00:00:00.
* **`data_format`**: The format of the data to parse (Required)
  * accepted values: `RAW, RAWTAIL, CSV, CSVTAIL, XLS, XLSX, JSON, JSONTAIL, AVRO, or XML`.
  * TAIL formats keep track of the current file being read & the position in the file.
  * Default is json
* **`timestamp_format`**: Format of the timestamp, in python [arrow](https://arrow.readthedocs.io/en/latest/#supported-tokens). If the timestamp is in Unix epoch, this can be set to `epoch`.
  * If the timestamp is split over multiple fields, curlies can be used to indicate formatting, ie: `YYYY-MM-DD HH:mm:ss ZZ`
  * If the timestamp can be in one of multiple fields, a priority list of field names can be given: `timestamp1,timestamp2`.
* **`timezone`**: Timezone of the timestamp data stored in/returned by the DB. (Optional)
  * Note: if timezone information is not included in the data returned by the DB, then this field has to be specified. 
* **`timestamp_field`**: Field name for the timestamp. (Required)
  * Default is `timestamp`.
* **`target_timestamp_timezone`**: Timezone of the timestamp data to be sent and stored in InsightFinder.
  * Default value is UTC
  * Only if you wish to store data with a time zone other than UTC, this field should be specified to be the desired time zone.
* **`component_field`**: Field name for the component name. (Optional)
* **`default_component_name`**: Default component name if component_field is not set or field value is empty. (Optional)
* **`instance_field`**: Field name for the instance name. (Optional, but highly recommended)
  * If not set or the field is not found, the instance name is the `Application`
  * Can also set instance name from multiple fields which separated by commas. Ex: `instance_name_part1,instance_name_part2`.
* **`dynamic_host_field`**: Field names used to get host id dynamically. (Optional)
* **`instance_whitelist`**: This field is a regex string used to define which instances will be filtered. (Optional)
* **`device_field`**: Field name for the device/container for containerized projects. (Optional)
  * Can also set device name from multiple fields separated by commas. Ex: `device_name_part1,device_name_part2`.
* **`instance_connector`**: The connector for building `instance_field` or `device_field` from multiple fields. (Optional)
  * Default is `-`.
* **`thread_pool`**: Number of thread to used in the pool. (Optional)
  * Default is 20.
* **`processes`**: Number of processes to run. (Optional)
* **`timeout`**: Minutes before which processes timeout. (Optional)
  * Default is 5 min.
* **`agent_http_proxy`**: HTTP proxy used to connect to the agent. (Optional)
* **`agent_https_proxy`**: HTTPS proxy used to connect to the agent. (Optional)

**InsightFinder Settings**
* **`user_name`**: User name in InsightFinder. (Required)
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. (Required)
* **`project_name`**: Name of the project created in the InsightFinder UI. (Required)
  * If this project does not exist, agent will create it automatically.
* **`system_name`**: Name of System owning the project. (Required)
  * If project_name does not exist in InsightFinder, agent will create a new system automatically from this field or project_name. 
* **`project_type`**: Type of the project (Required)
  * Accepted Values: `metric, metricreplay, log, logreplay, alert, alertreplay, incident, incidentreplay, deployment, deploymentreplay, trace, tracereplay`.
* **`containerize`**: Set to `YES` if project is a container project. (Required)
  * Default: no
* **`dynamic_metric_type`**: Metric Type in project settings (Required)
  * Set to empty to create normal projects'
  * Set to 'vm' to use 'DynamicVM' as the AgentType
  * Set to 'host' to use 'DynamicHost' as the AgentType
* **`sampling_interval`**: How frequently (in Minutes) data is collected. Should match the interval used in project settings. (Required)
* **`run_interval`**: How frequently (in Minutes) the agent is run. Should match the interval used in cron. (Required)
* **`chunk_size_kb`**: Size of chunks (in KB) to send to InsightFinder. (Optional)
  * Default is `2048`.
* **`if_url`**: URL for InsightFinder. (Required)
  * Default is `https://app.insightfinder.com`.
* **`if_http_proxy`**: HTTP proxy used to connect to InsightFinder. (Optional)
* **`if_https_proxy`**: HTTPS proxy used to connect to InsightFinder. (Optional)
