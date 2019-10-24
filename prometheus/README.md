## Installing the Agent
**Download the agent [tarball](https://github.com/insightfinder/InsightAgent/raw/master/prometheus/prometheus.tar.gz) and untar it:**
```
wget https://github.com/insightfinder/InsightAgent/raw/master/prometheus/prometheus.tar.gz
tar xvf prometheus.tar.gz && cd prometheus
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
python getmessages_prometheus.py -t
```

**If satisfied with the output, configure the agent to run continuously:**
```
sudo ./cron-config.sh <sampling_interval>
```

### Config Variables
<!-- * `alert_filters_include`: Used to filter messages based on allowed values.
* `alert_filters_exclude`: Used to filter messages based on unallowed values. 
* `alert_data_fields`: Comma-delimited list of field names to use as data fields. If not set, all fields will be reported.
-->
* `prometheus_uri`: URI to Prometheus API as `scheme://host:port`. For example, `http://localhost:9090`.
* `metrics`: Metrics to query Prometheus for. If none specified, all metrics returned from `/api/v1/label/__names__/values` will be used.
* `query_label_selector`: Label selector to use when querying for metrics, such as `{namespace="monitoring"}`. 
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI.
* `token`: Token from your Account Profile in the InsightFinder UI.
* **`project_name`**: Name of the project created in the InsightFinder UI.
* **`project_type`**: Type of the project - Set to `metric` <!-- and optionally (separated by a comma), one of [log, incident, alert, deployment]` ie `metric,alert`. -->
* **`sampling_interval`**: How frequently data is collected. Should match the interval used in cron.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`. This should be kept large so that all metrics for a given timestamp are sent at once, otherwise data loss may occur due to overwriting partial data previously sent with partial results.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.
