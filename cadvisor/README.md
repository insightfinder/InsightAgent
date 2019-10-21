# cAdvisor
## Installing the Agent
**Download the agent [tarball](https://github.com/insightfinder/InsightAgent/raw/master/cadvisor/cadvisor.tar.gz) and untar it:**
```
wget https://github.com/insightfinder/InsightAgent/raw/master/cadvisor/cadvisor.tar.gz
tar xvf cadvisor.tar.gz && cd cadvisor
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
python getmetrics_cadvisor.py -t
```

**If satisfied with the output, configure the agent to run continuously:**
```
sudo ./cron-setup.sh
```

### Config Variables
* **`api_uri`**: URI used for REST API requests as scheme://host:port.
* `data_fields`: Comma-delimited list of metrics to report, selected from cpu, memory, network, filesystem, and diskio. If not set, all fields will be reported.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI.
* `token`: Token from your Account Profile in the InsightFinder UI.
* **`project_name`**: Name of the project created in the InsightFinder UI.
* **`project_type`**: Type of the project - one of `metric, metricreplay, log, logreplay, incident, incidentreplay, alert, alertreplay, deployment, deploymentreplay`.
* **`sampling_interval`**: How frequently data is collected. Must be set to 90s
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.
