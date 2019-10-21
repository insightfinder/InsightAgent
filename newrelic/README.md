# New Relic
## Installing the Agent
**Download the agent [tarball](https://github.com/insightfinder/InsightAgent/raw/master/newrelic/newrelic.tar.gz) and untar it:**
```
tar xvf newrelic.tar.gz && cd newrelic
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
python getmetrics_newrelic.py -t
```

**If satisfied with the output, configure the agent to run continuously:**
```
sudo ./cron-setup.sh <sampling_interval>
```

### Config Variables
* **`api_key`**: API key for New Relic.
* `app_or_host`: APP, HOST, or BOTH, depending on what type of metrics to collect.
* `auto_create_project`: Set to `YES` to send data to a project based on the app name, which will be automatically created if it doesn't exist.
* `containerize`: Set to `YES` to treat each host as a device within the app. Only applies when `app_or_host` is `HOST` or `BOTH`
* `app_name_filter`: A comma-delimited list of app names to include. Default is all app names.
* `app_id_filter`: A comma-delimited list of app IDs to include. Default is all app IDs.
* `host_filter`: A comma-delimited list of hosts to include. Default is all hosts.
* `app_metrics`: A comma-delimited list of app_metric_name:value|value. Default is `Apdex:score,EndUser/Apdex:score,HttpDispatcher:average_call_time|call_count,WebFrontend/QueueTime:average_call_time|call_count,Errors/all:error_count`
* `host_metrics`: A comma-delimited list of host_metric_name:value|value. Default is `CPU/User Time:percent,Memory/Heap/Used:used_mb_by_host,Memory/Physical:used_mb_by_host,Instance/connectsReqPerMin:requests_per_minute,Controller/reports/show:average_response_time|calls_per_minute|call_count|min_response_time|max_response_time|average_exclusive_time|average_value|total_call_time_per_minute|requests_per_minute|standard_deviation|throughput|average_call_time|min_call_time|max_call_time|total_call_time`
* **`run_interval`**: How frequently (in min) this agent is ran.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI.
* `token`: Token from your Account Profile in the InsightFinder UI.
* **`project_name`**: Name of the project created in the InsightFinder UI.
* `system_name`: System name to add to each project data is sent to from this agent.
* **`sampling_interval`**: How frequently data is collected. Should match the interval used in cron.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.
