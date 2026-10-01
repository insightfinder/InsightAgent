# Zabbix Agent

Collects metrics (and optionally alerts/logs) from the Zabbix API and sends them to InsightFinder.

- Requires Python 3.8+ on a Linux host that can reach both the Zabbix API and InsightFinder.
- Each `*.ini` file in `conf.d/` is one job (e.g. one InsightFinder project). All of them are processed on every run.

## Installation

### 1. Get the agent

```bash
git clone https://github.com/insightfinder/InsightAgent.git
cd InsightAgent/zabbix
```

Or copy just the `zabbix/` directory to the target host. The steps below assume you are inside that directory. Run `pwd` to get its absolute path, which the cron job in step 5 needs.

### 2. Set up the Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate
```

### 3. Configure

```bash
cp conf.d/config.ini.template conf.d/config.ini
vi conf.d/config.ini
```

At a minimum, set:

| Section          | Key                                            | Description                                                                 |
|------------------|------------------------------------------------|-----------------------------------------------------------------------------|
| `[zabbix]`       | `url`, `user`, `password`                      | Zabbix server URL and API credentials                                       |
| `[insightfinder]`| `user_name`, `license_key`                     | InsightFinder user and license key (Account Profile in the InsightFinder UI)|
| `[insightfinder]`| `project_name`, `system_name`                  | Target project/system. These are created automatically if they don't exist.  |
| `[insightfinder]`| `project_type`                                 | Usually `metric`. Use `alert` or `log` for alert/log collection.            |
| `[insightfinder]`| `sampling_interval`, `run_interval`            | Both should be `5` (minutes) to match the cron schedule below               |
| `[insightfinder]`| `if_url`                                       | InsightFinder URL, default `https://app.insightfinder.com`                  |

To send data to more than one project, add one `.ini` file per project in `conf.d/`. Only files ending in `.ini` are loaded, so the `.template` file is ignored.

### 4. Test

Testing mode collects and parses data but doesn't send anything to InsightFinder:

```bash
./venv/bin/python getmessages_zabbix.py -t
```

Then do one real run and confirm that data shows up in the InsightFinder project:

```bash
./venv/bin/python getmessages_zabbix.py
```

### 5. Schedule with cron (every 5 minutes)

```bash
crontab -e
```

Add this line, replacing `/path/to/zabbix` with the absolute path from step 1:

```cron
*/5 * * * * cd /path/to/zabbix && ./venv/bin/python getmessages_zabbix.py >> /path/to/zabbix/agent.log 2>&1
```

Check the entry with `crontab -l`, and watch `agent.log` after the next 5-minute mark.

Alternatively, put the job in a file under `/etc/cron.d/`, for example `/etc/cron.d/insightagent-zabbix`. Unlike `crontab -e`, entries in this file need a user field (here `ubuntu`) before the command:

```cron
*/5 * * * * ubuntu cd /path/to/zabbix && ./venv/bin/python getmessages_zabbix.py >> /path/to/zabbix/agent.log 2>&1
```

The file must be owned by root and must not be group- or world-writable (`chmod 644`). Cron skips files whose names contain a `.`, so don't give it an extension.

## Configuration reference

[conf.d/config.ini.template](conf.d/config.ini.template) has a comment on every option. The ones used most often:

**Filtering what gets collected (`[zabbix]`)**
- `host_groups`: Pipe-separated (`|`) host group names. Empty means all host groups.
- `hosts`: Hosts to query. Empty means all hosts.
- `host_blocklist`: Comma-separated hosts to skip, given as IDs, names, or regexes.
- `template_ids`: Collect the items defined in these templates.
- `collect_dedicated_items`: Also collect items that aren't part of a template.
- `metric_allowlist` / `metric_disallowlist`: Comma-separated metric names or regexes. Wrap a regex in `/`, e.g. `/^CPU.*/`.
- `his_time_range`: Backfill a time range, e.g. `2020-04-14 00:00:00,2020-04-15 00:00:00`.

**Instance/component naming (`[zabbix]`)**
- `instance_field`: Default `hostid`.
- `component_from_host_group`, `component_from_instance_name_re_sub`: Derive the component name from the host group, or from the instance name with `re.sub` pairs.
- `component_name_script`: Path to a Python file that defines `generate_component_name(instance_name, hostgroup_name, tags)`. It takes precedence over the two options above. See [component_name_script.py](component_name_script.py).
- `zone_from_host_group`, `subzone_from_instance_name_regex`: Zone and subzone mapping.

**Metric post-processing (`[zabbix]`)**
- `metric_transform_script`: Rename metrics or transform their values. See [metric_transforms_example.py](metric_transforms_example.py).
- `derived_metrics_script`: Create synthetic metrics from conditions on tags and other metrics. See [derived_metrics_example.py](derived_metrics_example.py).

**Performance and load on the Zabbix server (`[zabbix]`)**
- `max_workers`: Parallel workers. Default is the number of CPU cores, capped at 10.
- `max_host_per_request`: Default 100.
- `request_timeout`: In seconds. Default 60.
- `request_delay_ms`: Delay between consecutive API calls. Default 0.
- `max_concurrent_zabbix`: Maximum number of `conf.d` files allowed to query the Zabbix server at the same time. Default is unlimited.

**Proxies**
- `agent_http_proxy` / `agent_https_proxy` in `[zabbix]`: Proxy used to reach Zabbix.
- `if_http_proxy` / `if_https_proxy` in `[insightfinder]`: Proxy used to reach InsightFinder.

## One config per host group

For setups that send each Zabbix host group to its own project, [generate_hostgroup_configs.py](generate_hostgroup_configs.py) creates a `conf.d/<host-group>-metrics.ini` for every host group, based on [zabbix.ini.template](zabbix.ini.template). See [generate_hostgroup_configs_README.md](generate_hostgroup_configs_README.md).
