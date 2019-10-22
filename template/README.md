# Template
This is a template for developing new agents.
To start a new agent, recursively copy this folder.
`cp -r template/ new_agent/ && cd new_agent`

In your new agent folder, rename the script
`mv insightagent-boilerplate.py getmessages_agent.py`

Depending on whether or not the agent should run on a cron (occasionally collect and send data) or monit (continuously monitor data). Delete the other script, then modify the needed script with the agent name and script name.
```
$ vi {cron-setup.sh|monit-setup.sh}
...
AGENT="new_agent"
AGENT_SCRIPT="getmessages_agent.py"
...
```

Start writing your new agent, modifying `config.ini.template` to have the required input parameters. If your script requires a new pip package, download the `.whl` or `.tar.gz`, place it in pip_packages, then update `pip-setup.sh`.

Once you're done, create a tar for the agent and move it into the agent folder.

```
cd ..
tar -czvf new_agent.tar.gz
mv new_agent.tar.gz new_agent
```

Then, delete this section from the `README.md` and update it as appropriate.

## Installing the Agent
**Download the agent [tarball](https://github.com/insightfinder/InsightAgent/raw/master/new_agent/new_agent.tar.gz) and untar it:**
```
wget https://github.com/insightfinder/InsightAgent/raw/master/new_agent/new_agent.tar.gz
tar xvf new_agent.tar.gz && cd new_agent
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
python getmessages_agent.py -t
```

**If satisfied with the output, configure the agent to run continuously:**
```
sudo ./cron-setup.sh <sampling_interval>
or
sudo ./monit-setup.sh
```

### Config Variables
* `filters_include`: Used to filter messages based on allowed values.
* `filters_exclude`: Used to filter messages based on unallowed values.
* **`data_format`**: The format of the data to parse: CSV, JSON, or RAW
* **`csv_field_names`**: A list of field names for CSV input. Required, even if the CSV to parse has a header.
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
* **`sampling_interval`**: How frequently data is collected. Should match the interval used in cron.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.
