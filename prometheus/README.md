# prometheus
This agent collects data from prometheus and sends it to Insightfinder.
## Installing the Agent

### Short Version
```bash
bash <(curl -sS https://raw.githubusercontent.com/insightfinder/InsightAgent/master/utils/fetch-agent.sh) prometheus && cd prometheus
vi config.ini
sudo ./scripts/install.sh --create  # install on localhost
                                    ## or on multiple nodes
sudo ./scripts/remote-cp-run.sh list_of_nodes
```

See the `offline` README for instructions on installing prerequisites.

### Long Version
###### Download the agent tarball and untar it:
```bash
curl -sSLO https://github.com/insightfinder/InsightAgent/raw/master/prometheus/prometheus.tar.gz
tar xvf prometheus.tar.gz && cd prometheus
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
2to3 -w getmessages_prometheus.py; \
else echo "No upgrade needed"; fi
```

###### Setup pip & required packages:
```bash
sudo ./scripts/pip-config.sh
```

###### Test the agent:
```bash
python getmessages_prometheus.py -t
```

###### If satisfied with the output, configure the agent to run continuously:
```bash
sudo ./scripts/cron-config.sh
```

### Config Variables
* `prometheus_uri`: URI for Prometheus API as `scheme://host:port`. Defaults to `http://localhost:9090`
* `metrics`: Metrics to query for. If none specified, all metrics returned from `/api/v1/label/__names__/values` will be used.
* `metrics_to_ignore`: Comma-delimited metrics to not report. Defaults to `ALERTS,ALERTS_FOR_STATE`.
* `query_label_selector`: Label selector to use when querying for metrics, ie `{namespace="monitoring"}`.
* `alert_data_fields`: Data fields to report as alerts.
* `alert_filters_include`: Filter alert messages on allowed values.
* `alert_filters_exclude`: Fitler alert messages on disallowed values.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. 
* `token`: Token from your Account Profile in the InsightFinder UI. 
* **`project_name`**: Name of the project created in the InsightFinder UI. 
* `project_name_alert`: Name of the alert project created in the InsightFinder UI.
* **`project_type`**: Type of the project - one of `metric, metricreplay, log, logreplay, incident, incidentreplay, alert, alertreplay, deployment, deploymentreplay`.
* **`run_interval`**: How frequently the agent is ran. Should match the interval used in cron.
* **`sampling_interval`**: How frequently data is collected. Should match the interval used in project settings.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.
