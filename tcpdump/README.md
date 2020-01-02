# tcpdump
This agent collects data from tcpdump and sends it to Insightfinder.
## Installing the Agent

### Short Version
```bash
bash <(curl -sS https://raw.githubusercontent.com/insightfinder/InsightAgent/master/utils/fetch-agent.sh) tcpdump && cd tcpdump
vi config.ini
sudo ./setup/install.sh --create  # install on localhost
                                    ## or on multiple nodes
sudo ./setup/remote-cp-run.sh list_of_nodes
```

See the `offline` README for instructions on installing prerequisites.

### Long Version
###### Download the agent tarball and untar it:
```bash
curl -sSLO https://github.com/insightfinder/InsightAgent/raw/master/tcpdump/tcpdump.tar.gz
tar xvf tcpdump.tar.gz && cd tcpdump
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
sudo ./setup/remote-cp-run.sh list_of_nodes -f <nodelist_file>
```
Where `list_of_nodes` is a list of nodes that are configured in `~/.ssh/config` or otherwise reachable with `scp` and `ssh`.

#### Manual Install (local only)
###### Check Python version & upgrade if using Python 3
```bash
if [[ $(python -V 2>&1 | awk '{ print substr($NF, 1, 1) }') == "3" ]]; then \
2to3 -w getlogs_tcpdump.py; \
else echo "No upgrade needed"; fi
```

###### Setup pip & required packages:
```bash
sudo ./setup/pip-config.sh
```

###### Test the agent:
```bash
python getlogs_tcpdump.py -t
```

###### If satisfied with the output, configure the agent to run continuously:
```bash
sudo ./setup/cron-config.sh
```

### Config Variables
* `expression`: `tcpdump` expression. see tcpdump documentation (`man tcpdump`)
* `hex_ascii`: Display packet as 'hex', 'ascii', or 'both'. Defaults to not showing the packet contents.
* `abs_or_rel_seq`: Set to 'ABS' to display absolute sequence number. Default is relative.
* `interfaces`: Comma delimited list of interfaces to listen on. See tcpdump documentation for `--interface=`.
* `secret`: Secret to use for validating TCP segment digests. See tcpdump documentation for `-M`
* `filter`: Filter expression, direction, or file to use. See tcpdump documentation for `-Q` and `-F`.
* `data_fields`: Comma-delimited list of field names to use as data fields. If not set, all fields will be reported.
* `file_path`: If sending data to a replay project, and `project_type` contains 'replay', set this to a comma delimited list of files and directories containing pcap files
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. 
* `token`: Token from your Account Profile in the InsightFinder UI. 
* **`project_name`**: Name of the project created in the InsightFinder UI. 
* **`project_type`**: Type of the project - one of `metric, metricreplay, log, logreplay, incident, incidentreplay, alert, alertreplay, deployment, deploymentreplay`.
* `sampling_interval`: How frequently data is collected. Should match the interval used in project settings.
* `run_interval`: How frequently the agent is ran. Should match the interval used in cron.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.
