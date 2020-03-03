# servicenow
This agent collects data from servicenow and sends it to Insightfinder.
## Installing the Agent

### Short Version
```bash
bash <(curl -sS https://raw.githubusercontent.com/insightfinder/InsightAgent/master/utils/fetch-agent.sh) servicenow && cd servicenow
vi config.ini
sudo ./setup/install.sh --create  # install on localhost
                                  ## or on multiple nodes
sudo ./offline/remote-cp-run.sh list_of_nodes
```

See the `offline` README for instructions on installing prerequisites.

### Long Version
###### Download the agent tarball and untar it:
```bash
curl -fsSLO https://github.com/insightfinder/InsightAgent/raw/master/servicenow/servicenow.tar.gz
tar xvf servicenow.tar.gz && cd servicenow
```

###### Set up `config.ini`
```bash
python configure.py
```
See below for a further explanation of each variable. 

#### Automated Install (local or remote)
###### Review propsed changes from install:
```bash
sudo ./setup/install.sh
```

###### Once satisfied, run:
```bash
sudo ./setup/install.sh --create
```

###### To deploy on multiple hosts, instead call 
```bash
sudo ./offline/remote-cp-run.sh list_of_nodes -f <nodelist_file>
```
Where `list_of_nodes` is a list of nodes that are configured in `~/.ssh/config` or otherwise reachable with `scp` and `ssh`.

#### Manual Install (local only)
###### Check Python version & upgrade if using Python 3
```bash
if [[ $(python -V 2>&1 | awk '{ print substr($NF, 1, 1) }') == "3" ]]; then \
2to3 -w getlogs_servicenow.py; \
else echo "No upgrade needed"; fi
```

###### Setup pip & required packages:
```bash
sudo ./setup/pip-config.sh
```

###### Test the agent:
```bash
python getlogs_servicenow.py -t
```

###### If satisfied with the output, configure the agent to run continuously:
```bash
sudo ./setup/cron-config.sh
```

### Config Variables
* **`base_url`**: Base URL to build the API off of.
* **`api_endpoint`**: API endpoint to call.
* **`username`**: Username to authenticate with.
* **`password_encrypted`**: Password, encoded in base64. To set this, run `python configure.py`.
* `filters_include`: Used to filter messages based on allowed values.
* `filters_exclude`: Used to filter messages based on unallowed values.
* `json_top_level`: The top-level of fields to parse in JSON/AVRO/XML. For example, if all fields of interest are nested like 
* `timestamp_format`: Format of the timestamp, in python [strftime](http://strftime.org/). If the timestamp is in Unix epoch, this can be left blank or set to `epoch`. If the timestamp is split over multiple fields, curlies can be used to indicate formatting, ie: `{YEAR} {MO} {DAY} {TIME}`; alternatively, if the timestamp can be in one of multiple fields, a priority list of field names can be given: `timestamp1,timestamp2`.
* `timezone`: Timezone for the data. Note that it cannot be parsed from the timestamp, and will be discarded if only present there.
* `timestamp_field`: Field name for the timestamp. Default is `timestamp`.
* `instance_field`: Field name for the instance name. If not set or the field is not found, the instance name is the hostname of the machine the agent is installed on. This can also use curly formatting or a priority list.
* `device_field`: Field name for the device/container for containerized projects. This can also use curly formatting or a priority list.
* `data_fields`: Comma-delimited list of field names to use as data fields. If not set, all fields will be reported. Each data field can either be a field name (`name`) or a labeled field (`<name>:<value>` or `<name>:=<value>`), where `<name>` and `<value>` can be raw strings (`fieldname:fieldvalue`) or curly-formatted (`{na} [{me}]:={val} - {ue}`). If `:=` is used as the separator, `<value>` is treated as a mathematical expression that can be evaluated with `eval()`.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. 
* `token`: Token from your Account Profile in the InsightFinder UI. 
* **`project_name`**: Name of the project created in the InsightFinder UI. 
* **`project_type`**: Type of the project - one of `metric, metricreplay, log, logreplay, incident, incidentreplay, alert, alertreplay, deployment, deploymentreplay`.
* **`sampling_interval`**: How frequently data is collected. Should match the interval used in project settings.
* **`run_interval`**: How frequently the agent is ran. Should match the interval used in cron.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.
