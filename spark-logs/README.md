# spark-logs
This agent collects data from spark-logs and sends it to Insightfinder.
## Installing the Agent

### Short Version
```bash
bash <(curl -sS https://raw.githubusercontent.com/insightfinder/InsightAgent/master/utils/fetch-agent.sh) spark-logs && cd spark-logs
vi config.ini
sudo ./scripts/install.sh --create  # install on localhost
                                    ## or on multiple nodes
sudo ./scripts/remote-cp-run.sh list_of_nodes
```

See the `offline` README for instructions on installing prerequisites.

### Long Version
###### Download the agent tarball and untar it:
```bash
curl -sSLO https://github.com/insightfinder/InsightAgent/raw/master/spark-logs/spark-logs.tar.gz
tar xvf spark-logs.tar.gz && cd spark-logs
```

###### Copy `config.ini.template` to `config.ini` and edit it:
```bash
cp config.ini.template config.ini
vi config.ini
```
See below for a further explanation of each variable.

#### Automated Install (local or remote)
###### Review propsed changes from install:
```bash
sudo ./scripts/install.sh
```

###### Once satisfied, run:
```bash
sudo ./scripts/install.sh --create
```

###### To deploy on multiple hosts, instead call 
```bash
sudo ./scripts/remote-cp-run.sh list_of_nodes -f <nodelist_file>
```
Where `list_of_nodes` is a list of nodes that are configured in `~/.ssh/config` or otherwise reachable with `scp` and `ssh`.

#### Manual Install (local only)
###### Check Python version & upgrade if using Python 3
```bash
if [[ $(python -V 2>&1 | awk '{ print substr($NF, 1, 1) }') == "3" ]]; then \
2to3 -w getlogs_spark.py; \
else echo "No upgrade needed"; fi
```

###### Setup pip & required packages:
```bash
sudo ./scripts/pip-config.sh
```

###### Test the agent:
```bash
python getlogs_spark.py -t
```

###### If satisfied with the output, configure the agent to run continuously:
```bash
sudo ./scripts/cron-config.sh
```

### Config Variables
* `history_server_uri`: URI for history server as `<scheme>://server:port`.
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
* `timestamp_field`: Field name for the timestamp. Default is `timestamp`.
* `instance_field`: Field name for the instance name. If not set or the field is not found, the instance name is the hostname of the machine the agent is installed on. 
* `device_field`: Field name for the device/container for containerized projects.
* `data_fields`: Comma-delimited list of field names to use as data fields. If not set, all fields will be reported.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. 
* `token`: Token from your Account Profile in the InsightFinder UI. 
* **`project_name`**: Name of the project created in the InsightFinder UI. 
* **`project_type`**: Type of the project - one of `metric, metricreplay, log, logreplay, incident, incidentreplay, alert, alertreplay, deployment, deploymentreplay`.
* **`sampling_interval`**: How frequently data is collected. Should match the interval used in project settings.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.
