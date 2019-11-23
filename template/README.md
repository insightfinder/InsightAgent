{{{
# Template
This is a template for developing new agents.
To start a new agent, recursively copy this folder.
```bash
cp -r template/* {{NEWAGENT}}/ && cd {{NEWAGENT}}
```

In your new agent folder, rename the script
```bash
mv insightagent-boilerplate.py {{NEWAGENT&script}}
```

Start writing your new agent, modifying `config.ini.template` to have the required input parameters.

Once you're done, update the documentation
```bash
../utils/genCONFIGVARS.sh
vi _CONFIGVARS.md
vi _SPECIAL.md # if there's additional documentation to add. Replaces `{{EXTRA}}` below.
```

Then, add make `requirements.txt` and add the pip packages:
```bash
../utils/pip-requirements.sh
```
and resolve any errors.

Add new files to github:
```bash
git add .
```

Finally, make the installer 
```bash
../utils/makeAgentInstaller.sh [--monit]
```
}}}
# {{NEWAGENT}}
This agent collects data from {{NEWAGENT}} and sends it to Insightfinder.
{{EXTRA}}
## Installing the Agent

### Short Version
```bash
bash <(curl https://raw.githubusercontent.com/insightfinder/InsightAgent/master/utils/get-agent.sh) {{NEWAGENT}} && cd {{NEWAGENT}}
vi config.ini
sudo ./install.sh --create # install on localhost
## or 
sudo ./distrubute.sh list_of_nodes # install on each of list_of_nodes
```

### Long Version
**Download the agent [tarball](https://github.com/insightfinder/InsightAgent/raw/master/{{NEWAGENT}}/{{NEWAGENT}}.tar.gz) and untar it:**
```bash
curl -L https://github.com/insightfinder/InsightAgent/raw/master/{{NEWAGENT}}/{{NEWAGENT}}.tar.gz -o {{NEWAGENT}}.tar.gz
tar xvf {{NEWAGENT}}.tar.gz && cd {{NEWAGENT}}
```

**Copy `config.ini.template` to `config.ini` and edit it:**
```bash
cp config.ini.template config.ini
vi config.ini
```
See below for a further explanation of each variable.

#### Automated Install
**Review propsed changes from install:**
```bash
sudo ./install.sh
```

**Once satisfied, run:**
```bash
sudo ./install.sh --create
```

#### Manual Install (localhost only)
**Check Python version & upgrade if using Python 3**
```bash
if [[ $(python -V 2>&1 | awk '{ print substr($NF, 1, 1) }') == "3" ]]; then \
2to3 -w {{NEWAGENT&script}}; \
else echo "No upgrade needed"; fi
```

**Setup pip & required packages:**
```bash
sudo ./pip-config.sh
```

**Test the agent:**
```bash
python {{NEWAGENT&script}} -t
```

**If satisfied with the output, configure the agent to run continuously:**
```bash
sudo ./{{NEWAGENT&cronit}}
```

### On Multiple Hosts
In order to install this agent on multiple hosts, instead of calling `./install.sh --create`, simply run
```bash
./distribute.sh list_of_nodes
```
Where `list_of_nodes` is a list of nodes that are configured in `~/.ssh/config` or otherwise reachable with `scp` and `ssh`.

{{CONFIGVARS}}
