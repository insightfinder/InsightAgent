# tcpdump
This agent collects data from tcpdump and sends it to Insightfinder.
## Installing the Agent

### Short Version
```bash
bash <(curl -sS https://raw.githubusercontent.com/insightfinder/InsightAgent/master/utils/fetch-agent.sh) tcpdump && cd tcpdump
vi config.ini
sudo ./scripts/install.sh --create  # install on localhost
                                    ## or on multiple nodes
sudo ./scripts/remote-cp-run.sh list_of_nodes
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
2to3 -w getlogs_tcpdump.py; \
else echo "No upgrade needed"; fi
```

###### Setup pip & required packages:
```bash
sudo ./scripts/pip-config.sh
```

###### Test the agent:
```bash
python getlogs_tcpdump.py -t
```

###### If satisfied with the output, configure the agent to run continuously:
```bash
sudo ./scripts/cron-config.sh
```

