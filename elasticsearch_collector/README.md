# Elasticsearch Collector
This agent collects data from elasticsearch and sends it to Insightfinder.
## Installing the Agent

### Required Dependencies:
1. Python 3.6.8
1. Pip3

###### Installation Steps:
1. Download the elasticsearch_collector.tar.gz package
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
The config.ini file contains all of the configuration settings needed to connect to the Elasticsearch instance and to stream the data to InsightFinder.

The password for the Elasticsearch user will need to be obfuscated using the ifobfuscate.py script.  It will prompt you for the password and provide the value to add to the configuration file. 

```
python ./ifobfuscate.py 
```

The configure_python.sh script will generate a config.ini file for you; however, if you need to create a new one, you can simply copy the config.ini.template file over the config.ini file to start over. 

Populate all of the necessary fields in the config.ini file with the relevant data.  More details about each field can be found in the comments of the config.ini file and the Config Variables below. 

###### Test the agent:
Once you have finished configuring the config.ini file, you can test the agent to validate the settings. 

This will connect to the Elasticsearch instance, but it will not send any data to InsightFinder. This allows you to verify that you are getting data from Prometheus and that there are no failing exceptions in the agent configuration.

User `-p` to define max processes, use `--timeout` to define max timeout.

```bash
./setup/test_agent.sh
```

###### Run agent with cron:
For the agent to run continuously, it will need to run as a cron job with `cron.py`. Every config file will start a cron job.

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
**ElasticSearch Settings**
* **`es_uris`**: A comma delimited list of RFC-1738 formatted urls. (Required)
  * Example: `<scheme>://[<username>:<password>@]hostname:port`
  * Username and Password are optional above, and can be provided below as well
* **`query_json`**: Query in json format for elasticsearch. (Optional*)
  * Not needed if providing a json file for query
* **`query_json_file`**: Json file to add to query body. (Optional*)
  * Not needed if providing query_json above
* **`query_chunk_size`**: The maximum number of messages for each query.
  * Default is 5000, max is 10000.
* **`indeces`**: Indeces to search over. (Required)
  * can list multiple indeces seperated by commma
  * Regex/wildcards supported
* **`query_time_offset_seconds`**: The time offset when querying live data w.r.t current time
  * Default is `0`
* **`port`**: Port to connect to where ElasticSearch is running. (Optional)
  * Overriden if port provided in URL
* **`http_auth`**: `username:password` used to connect to ElasticSearch. (Optional)
  * Overridden if provided in the URL
* **`use_ssl`**: True or False if SSL should be used. (Optional)
  * Overridden if URI scheme is `https`
* **`ssl_version`**: Version of SSL to use. (Optional)
  * Accepted values: `SSLv23 (default), SSLv2, SSLv3, TLSv1`
* **`ssl_assert_hostname`**: True or False if hostname verification should be enabled. (Optional)
* **`ssl_assert_fingerprint`**: True or False if fingerprint verification should be enabled. (Optional)
* **`verify_certs`**: True or False if certificates should be verified. (Optional)
* **`ca_certs`**: Path to CA bundle. (Optional)
* **`client_cert`**: Path to client certificate. (Optional)
* **`client_key`**: Path to client key. (Optional)
* **`his_time_range`**: Historical data time range. (Optional)
  * If this option is set, the agent will query metric values by time range.
  * Example: `2020-04-14 00:00:00,2020-04-15 00:00:00`
* **`project_field`**: Field name in response for the project name. (Optional)
  * If this field is empty, agent will use project_name in insightfinder section. 
* **`project_whitelist`**: Regex string used to define which projects form project_field will be filtered. (Optional)
* **`timestamp_format`**: Format of the timestamp, in python [arrow](https://arrow.readthedocs.io/en/latest/#supported-tokens). If the timestamp is in Unix epoch, this can be set to `epoch`.
  * If the timestamp is split over multiple fields, curlies can be used to indicate formatting, ie: `YYYY-MM-DD HH:mm:ss ZZ`
  * If the timestamp can be in one of multiple fields, a priority list of field names can be given: `timestamp1,timestamp2`.
* **`timezone`**: Timezone of the timestamp data stored in/returned by the DB. (Optional)
  * Note: if timezone information is not included in the data returned by the DB, then this field has to be specified. 
* **`timestamp_field`**: Field name for the timestamp. (Required)
  * Default is `@timestamp`.
  * If document_root_field is "", need to set the full path. For example _source.@timestamp
* **`target_timestamp_timezone`**: Timezone of the timestamp data to be sent and stored in InsightFinder.
  * Default value is UTC
  * Only if you wish to store data with a time zone other than UTC, this field should be specified to be the desired time zone.
* **`document_root_field`**: Defines the root for fields below. (Optional)
  * Default is `_source`
  * To use the whole document as the root, use ""
* **`component_field`**: Field name for the component name. (Optional)
* **`default_component_name`**: Default component name if component_field is not set or field value is empty. (Optional)
* **`instance_field`**: Field name for the instance name. (Optional)
  * If no value given, the elasticsearch's server name will be used.
* **`instance_field_regex`**: Field name and regex for the instance name. (Optional)
  * If no match or empty, will use `instance_field` setting
* **`instance_whitelist`**: This field is a regex string used to define which instances will be filtered. (Optional)
* **`default_instance_name`**: Default instance name if not set/found from above. (Optional)
* **`device_field`**: Field name for the device/container for containerized projects.
  * Can be set as a priority list: `device1,device2`.
  * If document_root_field is "", need to set the full path. For example _source.device
* **`device_field_regex`**: Regex to retrieve the device name using a capture group named 'device'. (Optional)
  * Example: `'(?P<device>.*)'`
* **`data_fields`**: Comma-delimited list of field names to use as data fields. (Optional)
  * Each data field can either be a field name (`name`) or regex.
  * If it is empty, the whole document at the document root will be sent.
  * Example: `Example: data_fields = /^system\.filesystem.*/,system.process.cgroup.memory.memsw.events.max`
* **`aggregation_data_fields`**: Fields to aggregrate in query/response, string or regex separated by commas. (Optional)
  * Example: `/0-metric\.values\.99.0/,value,doc_count`
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
  * Accepted Values: `metric, metricreplay, log, logreplay, incident, incidentreplay, alert, alertreplay, deployment, deploymentreplay`.
* **`containerize`**: Set to `YES` if project is a container project. (Required)
  * Default: `no`
* **`enable_holistic_model`**: Enable holistic model when auto creating project. (Optional)
  * Default is `false`.
* **`sampling_interval`**: How frequently (in Minutes) data is collected. Should match the interval used in project settings. (Required)
  * Default is `10`
* **`frequency_sampling_interval`**: How frequently (in Minutes) the hot/cold events are detected.
  * Default value is `10`
* **`log_compression_interval`**: How frequently (in Minutes) the log messages are compressed. (Optional)
  * Default value: `1`
* **`enable_log_rotation`**: Enable/Disable daily log rotation. (Optional)
  * `True` or `False`
* **`log_backup_count`**: The number of the log files to keep when `enable_log_rotation` is `true`. (Optional)
* **`run_interval`**: How frequently (in Minutes) the agent is run. (Required)
  * Should match the interval used in cron.
  * Default value: `10`
* **`worker_timeout`**: Timeout (in Minutes) for the worker process. (Optional)
  * Default is same as `run_interval`.
* **`chunk_size_kb`**: Size of chunks (in KB) to send to InsightFinder. (Optional)
  * Default is `2048`.
* **`if_url`**: URL for InsightFinder. (Required)
  * Default is `https://app.insightfinder.com`.
* **`if_http_proxy`**: HTTP proxy used to connect to InsightFinder. (Optional)
* **`if_https_proxy`**: HTTPS proxy used to connect to InsightFinder. (Optional)

