# Spark Logs
## Installing the Agent
**Download the agent [tarball](https://github.com/insightfinder/InsightAgent/raw/master/spark-logs/spark-logs.tar.gz) and untar it:**
```
wget https://github.com/insightfinder/InsightAgent/raw/master/spark-logs/spark-logs.tar.gz
tar xvf spark-logs.tar.gz && cd spark-logs
```

**Copy `config.ini.template` to `config.ini` and edit it:**
```
cp config.ini.template config.ini
vi config.ini
```
See below for a further explanation of each variable.

**Setup pip & required packages:**
```
sudo ./pip-setup.sh
```

**Test the agent:**
```
python getlogs_spark.py -t
```

**If satisfied with the output, configure the agent to run continuously:**
```
sudo ./cron-config.sh <sampling_interval>
```

### Config Variables
* **`history_server_uri`**: Set to the uri for the history server as `scheme://host:port`.
* `YARN_cluster`: Set to `YES` if this is set up as a YARN cluster.
* `filters_include`: Used to filter messages based on allowed values.
* `filters_exclude`: Used to filter messages based on unallowed values.
* `json_top_level`: The top-level of fields to parse in JSON. For example, if all fields of interest are nested like 
```
{ 
  "output": {
    "parsed": {
      "time": time, 
      "log": log message,
      ...
    }
    ...
  }
  ...
}
```
then this should be set to `output.parsed`.
* `timestamp_format`: Format of the timestamp, in python [strftime](http://strftime.org/). If the timestamp is in Unix epoch, this can be left blank or set to `epoch`.
* `timestamp_field`: Field name for the timestamp. Default is `completionTime`.
* `instance_field`: Field name for the instance name. Default is `name`. If not set or the field is not found, the instance name is the hostname of the machine the agent is installed on.
* `device_field`: Field name for the device/container for containerized projects.
* `data_fields`: Comma-delimited list of field names to use as data fields. If not set, all fields will be reported.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI.
* `token`: Token from your Account Profile in the InsightFinder UI.
* **`project_name`**: Name of the project created in the InsightFinder UI.
* **`project_type`**: Type of the project - one of `metric, metricreplay, log, logreplay, incident, incidentreplay, alert, alertreplay, deployment, deploymentreplay`.
* **`sampling_interval`**: How frequently data is collected. Should match the interval used in cron.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.
