{{{
# Template
This is a template for developing new agents.
To start a new agent, recursively copy this folder.
```bash
mkdir -p {{NEWAGENT}} && cp -r template/* {{NEWAGENT}}/ && cd {{NEWAGENT}}
```

In your new agent folder, rename the script
```bash
mv insightagent-boilerplate.py {{NEWAGENT@script}}
```

Start writing your new agent, modifying `config.ini.template` to have the required input parameters.

Once you're done, update the documentation
```bash
../utils/generate-CONFIGVARS.sh
vi .CONFIGVARS.md   
vi .EXTRA.md        # if there's additional documentation to add. Replaces `{{EXTRA}}` below.
```

<!-- Process in progress -->
If there are offline packages to add, put them in the `./offline/` folder. There are scripts which can help install from source if
1. The source is a git repo
2. It is installed using `./configure && make && make install`
CLI args can be avoided by setting the full repo in `./offline/target`. See `sar` for an example of this.
Much like this README.md, there are `{{REPLACEMENTS}}` in `./offline/README.md`.

Finally, make the installer 
```bash
../utils/make-agent-installer.sh [--monit]
```
}}}
# {{NEWAGENT}}
This agent collects data from {{NEWAGENT}} and sends it to Insightfinder.
{{EXTRA}}
## Installing the Agent

### Short Version
```bash
bash <(curl -sS https://raw.githubusercontent.com/insightfinder/InsightAgent/master/utils/fetch-agent.sh) {{NEWAGENT}} && cd {{NEWAGENT}}
vi config.ini
sudo ./setup/install.sh --create  # install on localhost
                                  ## or on multiple nodes
sudo ./offline/remote-cp-run.sh list_of_nodes
```

See the `offline` README for instructions on installing prerequisites.

### Long Version
###### Download the agent tarball and untar it:
```bash
curl -fsSLO https://github.com/insightfinder/InsightAgent/raw/master/{{NEWAGENT}}/{{NEWAGENT}}.tar.gz
tar xvf {{NEWAGENT}}.tar.gz && cd {{NEWAGENT}}
```

###### Set up `config.ini`
```bash
python configure.py
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
2to3 -w {{NEWAGENT@script}}; \
else echo "No upgrade needed"; fi
```

###### Setup pip & required packages:
```bash
sudo ./setup/pip-config.sh
```

###### Test the agent:
```bash
python {{NEWAGENT@script}} -t
```

###### If satisfied with the output, configure the agent to run continuously:
```bash
sudo ./setup/{{NEWAGENT@cronit}}
```

{{CONFIGVARS}}
