# k8s_logs
This agent collects data from k8s_logs and sends it to Insightfinder.
## Installing the Agent

### Short Version
```bash
bash <(curl -sS https://raw.githubusercontent.com/insightfinder/InsightAgent/master/utils/fetch-agent.sh) k8s_logs && cd k8s_logs
vi config.ini
sudo ./setup/install.sh --create  # install on localhost
                                  ## or on multiple nodes
sudo ./offline/remote-cp-run.sh list_of_nodes
```

See the `offline` README for instructions on installing prerequisites.

### Long Version
###### Download the agent tarball and untar it:
```bash
curl -fsSLO https://github.com/insightfinder/InsightAgent/raw/master/k8s_logs/k8s_logs.tar.gz
tar xvf k8s_logs.tar.gz && cd k8s_logs
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
2to3 -w getlogs_k8s.py; \
else echo "No upgrade needed"; fi
```

###### Setup pip & required packages:
```bash
sudo ./setup/pip-config.sh
```

###### Test the agent:
```bash
python getlogs_k8s.py -t
```

###### If satisfied with the output, configure the agent to run continuously:
```bash
sudo ./setup/cron-config.sh
```

### Config Variables
* `filters_include`: Used to filter messages based on allowed values.
* `filters_exclude`: Used to filter messages based on unallowed values.
* `namespace`: Namespaces to include.
* `pod_names`: Pod names to inlcude.
* `pod_field_selector`: Selector for pod field.
* `pod_label_selector`: Selector for pod label.
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
