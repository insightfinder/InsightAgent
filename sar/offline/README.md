# sar
This agent collects data from sar and sends it to Insightfinder.
## Installing the Agent

### Short Version
```bash
bash <(curl -sS https://raw.githubusercontent.com/insightfinder/InsightAgent/master/utils/fetch-agent.sh) sar && cd sar
vi config.ini
sudo ./install.sh --create # install on localhost
## or 
sudo ./remote-cp-run.sh list_of_nodes # install on each of list_of_nodes
```

### Long Version
**Download the agent [tarball](https://github.com/insightfinder/InsightAgent/raw/master/sar/sar.tar.gz) and untar it:**
```bash
curl -sSL https://github.com/insightfinder/InsightAgent/raw/master/sar/sar.tar.gz -o sar.tar.gz
tar xvf sar.tar.gz && cd sar
```

**Copy `config.ini.template` to `config.ini` and edit it:**
```bash
cp config.ini.template config.ini
vi config.ini
```
See below for a further explanation of each variable.

#### Automated Install (local or remote)
**Review propsed changes from install:**
```bash
sudo ./install.sh
```

**Once satisfied, run:**
```bash
sudo ./install.sh --create
```

To deploy on multiple hosts, instead call 
```bash
sudo ./remote-cp-run.sh list_of_nodes -f <nodelist_file>
```
Where `list_of_nodes` is a list of nodes that are configured in `~/.ssh/config` or otherwise reachable with `scp` and `ssh`.

#### Manual Install (local only)
**Check Python version & upgrade if using Python 3**
```bash
if [[ $(python -V 2>&1 | awk '{ print substr($NF, 1, 1) }') == "3" ]]; then \
2to3 -w getmetrics_sar.py; \
else echo "No upgrade needed"; fi
```

**Setup pip & required packages:**
```bash
sudo ./pip-config.sh
```

**Test the agent:**
```bash
python getmetrics_sar.py -t
```

**If satisfied with the output, configure the agent to run continuously:**
```bash
sudo ./cron-config.sh
```

