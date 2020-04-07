# mysql
This agent collects data from mysql and sends it to Insightfinder.
## Installing the Agent

### Short Version
```bash
bash <(curl -sS https://raw.githubusercontent.com/insightfinder/InsightAgent/master/utils/fetch-agent.sh) mysql && cd mysql
vi config.ini
sudo ./setup/install.sh --create  # install on localhost
                                  ## or on multiple nodes
sudo ./offline/remote-cp-run.sh list_of_nodes
```

See the `offline` README for instructions on installing prerequisites.

### Long Version
###### Download the agent tarball and untar it:
```bash
curl -fsSLO https://github.com/insightfinder/InsightAgent/raw/master/mysql/mysql.tar.gz
tar xvf mysql.tar.gz && cd mysql
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
2to3 -w getlogs_mysql.py; \
else echo "No upgrade needed"; fi
```

###### Setup pip & required packages:
```bash
sudo ./setup/pip-config.sh
```

###### Test the agent:
```bash
python getlogs_mysql.py -t
```

###### If satisfied with the output, configure the agent to run continuously:
```bash
sudo ./setup/cron-config.sh
```

### Config Variables
* `host`: mySQL host.
* `database`: Database to read from.
* `user`: User to authenticate as.
* `password`: Password to authenticate with.
* `table`: Table to connect to.
* `instance_name_column`: Column holding the instance name.
* `timestamp_column`: Column holding the timestamp.
* `timestamp_format`: Format of the timestamp, in python [strftime](http://strftime.org/). If the timestamp is in Unix epoch, this can be left blank or set to `epoch`.
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. 
* **`project_name`**: Name of the project created in the InsightFinder UI. 
* **`user_name`**: User name in InsightFinder
* `server_url`: IF URL.
* **`sampling_interval`**: How frequently data is collected. Should match the interval used in project settings.
