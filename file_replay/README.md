# file_replay
This agent collects data from file_replay and sends it to Insightfinder.
## Installing the Agent

### Short Version
```bash
bash <(curl -sS https://raw.githubusercontent.com/insightfinder/InsightAgent/master/utils/fetch-agent.sh) file_replay && cd file_replay
vi config.ini
sudo ./setup/install.sh --create  # install on localhost
                                  ## or on multiple nodes
sudo ./offline/remote-cp-run.sh list_of_nodes
```

See the `offline` README for instructions on installing prerequisites.

### Long Version
###### Download the agent tarball and untar it:
```bash
curl -fsSLO https://github.com/insightfinder/InsightAgent/raw/master/file_replay/file_replay.tar.gz
tar xvf file_replay.tar.gz && cd file_replay
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
2to3 -w getmessages_file_replay.py; \
else echo "No upgrade needed"; fi
```

###### Setup pip & required packages:
```bash
sudo ./setup/pip-config.sh
```

###### Test the agent:
```bash
python getmessages_file_replay.py -t
```

###### If satisfied with the output, configure the agent to run continuously:
```bash
sudo ./setup/cron-config.sh
```

### Config Variables
* `file_path`: Comma delimited list of files and directories to read files from.
* `file_name_regex`: Regex used to determine if a given file should be read (ie `^.*\.txt$` for text files).
* `filters_include`: Used to filter messages based on allowed values.
* `filters_exclude`: Used to filter messages based on unallowed values.
* **`data_format`**: The format of the data to parse: RAW, RAWTAIL, CSV, CSVTAIL, XLS, XLSX, JSON, JSONTAIL, AVRO, or XML. \*TAIL formats keep track of the current file being read & the position in the file.
* `raw_regex`: Regex used to parse raw data. Must use named capture groups `(?<name>...)` corresponding to fields defined below, as only those named capture groups will be reported.
* `raw_start_regex`: Regex used to indicate the start of a new multiline message. MUST start with `^` if defined.
* `csv_field_names`: A list of field names for CSV/XLS(X) input. Required, even if the CSV to parse has a header.
* `csv_field_delimiter`: A regex for the field delimiter to use - the default is `,|\t` for commas and tabs.
* `json_top_level`: The top-level of fields to parse in JSON/AVRO/XML. For example, if all fields of interest are nested like 
* `timestamp_format`: Format of the timestamp, in python [strftime](http://strftime.org/). If the timestamp is in Unix epoch, this can be left blank or set to `epoch`. If the timestamp is split over multiple fields, curlies can be used to indicate formatting, ie: `{YEAR} {MO} {DAY} {TIME}`; alternatively, if the timestamp can be in one of multiple fields, a priority list of field names can be given: `timestamp1,timestamp2`.
* `timezone`: Timezone for the data. Note that it cannot be parsed from the timestamp, and will be discarded if only present there.
* `timestamp_field`: Field name for the timestamp. Default is `timestamp`.
* `instance_field`: Field name for the instance name. If not set or the field is not found, the instance name is the hostname of the machine the agent is installed on. This can also use curly formatting or a priority list.
* `device_field`: Field name for the device/container for containerized projects. This can also use curly formatting or a priority list.
* `data_fields`: Comma-delimited list of field names to use as data fields. If not set, all fields will be reported. Each data field can either be a field name (`name`) or a labeled field (`<name>:<value>` or `<name>:=<value>`), where `<name>` and `<value>` can be raw strings (`fieldname:fieldvalue`) or curly-formatted (`{na} [{me}]:={val} - {ue}`). If `:=` is used as the separator, `<value>` is treated as a mathematical expression that can be evaluated with `numexpr.evaluate()`.
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
