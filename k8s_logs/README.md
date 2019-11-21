## Installing the Agent
**Download the agent [tarball](https://github.com/insightfinder/InsightAgent/raw/master/k8s_logs/k8s_logs.tar.gz) and untar it:**
```
wget https://github.com/insightfinder/InsightAgent/raw/master/k8s_logs/k8s_logs.tar.gz
tar xvf k8s_logs.tar.gz && cd k8s_logs
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
python getlogs_k8s.py -t
```

**If satisfied with the output, configure the agent to run continuously:**
```
sudo ./cron-config.sh <sampling_interval>
```

### Config Variables
* `namespaces`: Used to filter pods by namespace(s)
* `pod_names`: Used to filter pods by exact name
* `pod_field_selector`: Field selector to use when getting pods.
* `pod_label_selector`: Label selector to use when getting pods.
* `filters_include`: Used to filter messages based on allowed values.
* `filters_exclude`: Used to filter messages based on unallowed values.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI.
* `token`: Token from your Account Profile in the InsightFinder UI.
* **`project_name`**: Name of the project created in the InsightFinder UI.
* **`sampling_interval`**: How frequently data is collected. Should match the interval used in cron.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.
