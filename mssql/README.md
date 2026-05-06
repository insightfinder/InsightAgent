# MSSQL InsightFinder Agent

Collects metrics or logs from a Microsoft SQL Server database and streams them to InsightFinder.

---

## Installation

### Prerequisites (Linux/macOS)

```bash
# macOS
brew install freetds

# Linux (RHEL/CentOS)
yum install freetds
```

### Quick Install

```bash
bash <(curl -sS https://raw.githubusercontent.com/insightfinder/InsightAgent/master/utils/fetch-agent.sh) mssql && cd mssql
cp conf.d/config.ini.template conf.d/config.ini
vi conf.d/config.ini
sudo ./setup/install.sh --create
```

### Manual Install

```bash
# 1. Download
curl -fsSLO https://github.com/insightfinder/InsightAgent/raw/master/mssql/mssql.tar.gz
tar xvf mssql.tar.gz && cd mssql

# 2. Install dependencies
sudo ./setup/pip-config.sh

# 3. Configure
cp conf.d/config.ini.template conf.d/config.ini
vi conf.d/config.ini

# 4. Test
python getmessages_mssql.py -t

# 5. Schedule (cron)
sudo ./setup/cron-config.sh
```

### Windows Install

Download and unzip `getmessages_mssql-win.zip`, then:

```bat
cd getmessages_mssql
copy config.ini.template config.ini
# Edit config.ini, then test:
.\getmessages_mssql.exe -c config.ini -t
```

Schedule via Task Scheduler or `schtasks`:

```bat
schtasks /create /tn "InsightAgent" /tr "cmd /c C:\path\getmessages_mssql.exe -c C:\path\config.ini >> C:\path\output.log 2>&1" /sc minute /mo 10
```

---

## Configuration Reference

The config file has two sections: `[mssql]` (database and query settings) and `[insightfinder]` (destination settings).

---

### `[mssql]` — Database Connection

| Field | Required | Default | Description |
|---|---|---|---|
| `host` | Yes | `localhost` | MSSQL server hostname or IP |
| `user` | Yes | — | Database login user |
| `password` | Yes | — | Database login password |
| `database` | Yes | — | Database name to connect to |
| `port` | No | `1433` | TCP port |
| `timeout` | No | 0 (none) | Query timeout in seconds |
| `login_timeout` | No | 60 | Connection/login timeout in seconds |
| `appname` | No | — | Label shown in MSSQL activity monitor |

---

### `[mssql]` — Table Selection

```ini
# Static list
table_list = server_metrics, app_events

# Dynamic: SQL query that returns table names
table_list = sql:SELECT name FROM sys.tables WHERE name LIKE 'metrics_%'
```

The agent runs the configured `sql` query once per table in this list, substituting `{{table}}` with each table name.

---

### `[mssql]` — SQL Query

```ini
sql = """
      SELECT *
      FROM {{table}}
      WHERE {{timestamp_field}} >= '{{start_time}}' AND {{timestamp_field}} < '{{end_time}}';
      """
```

**Supported placeholders:**

| Placeholder | Replaced with |
|---|---|
| `{{table}}` | Each table from `table_list` |
| `{{timestamp_field}}` | The value of `timestamp_field` |
| `{{start_time}}` | Window start time |
| `{{end_time}}` | Window end time |

---

### `[mssql]` — Data Parsing

| Field | Required | Default | Description |
|---|---|---|---|
| `timestamp_field` | Yes | `timestamp` | Column that holds the event timestamp |
| `timestamp_format` | No | epoch | Arrow format string, e.g. `YYYY-MM-DD HH:mm:ss` |
| `timezone` | No | `UTC` | Timezone of timestamps stored in the DB |
| `target_timestamp_timezone` | No | `UTC` | Timezone InsightFinder stores data in |
| `instance_field` | No | hostname | Column whose value is used as the instance/host name |
| `device_field` | No | — | Column for an optional device identifier |
| `data_fields` | No | all columns | Comma-separated list of columns to send as data |
| `metric_name_field` | No | — | Column that holds the metric name (narrow/pivot format) |

---

### `[mssql]` — Instance Mapping

**Purpose:** Your data table stores a numeric or opaque ID in the instance column, but you want InsightFinder to show a human-readable name. Point these three fields at a lookup table and the agent will translate IDs to names automatically at startup.

| Field | Description |
|---|---|
| `instance_map_table` | Lookup table name |
| `instance_map_id_field` | Column in the lookup table that holds the raw ID |
| `instance_map_name_field` | Column in the lookup table that holds the display name |

**All three must be set together, or leave all three empty.**

#### How it works

1. At startup, the agent runs `SELECT * FROM <instance_map_table>`.
2. It builds an in-memory dictionary: `{ id_field_value → name_field_value }`.
3. For every data row, it looks up the value in `instance_field` against this dictionary and replaces it with the display name before sending to InsightFinder.
4. If a value is not found in the map, the original raw value is used unchanged.

#### Example

Suppose your data table `server_metrics` stores a numeric `server_id` instead of a hostname:

```
server_metrics
┌────────────────────────────────────────────────────────┐
│ ts                  │ server_id │ cpu_pct │ mem_pct    │
│ 2025-01-15 10:00:00 │ 42        │ 78.3    │ 55.1       │
│ 2025-01-15 10:00:00 │ 99        │ 12.0    │ 30.4       │
└────────────────────────────────────────────────────────┘
```

And you have a lookup table `host_registry`:

```
host_registry
┌──────────────────────────────────┐
│ id  │ hostname                   │
│ 42  │ web-prod-01.example.com    │
│ 99  │ db-prod-03.example.com     │
└──────────────────────────────────┘
```

Configure the mapping:

```ini
instance_field       = server_id
instance_map_table   = host_registry
instance_map_id_field   = id
instance_map_name_field = hostname
```

Result: InsightFinder receives `web-prod-01.example.com` and `db-prod-03.example.com` as instance names instead of `42` and `99`.

---

### `[mssql]` — Device Mapping

**Purpose:** Same concept as instance mapping, but for the *device* field. The resolved device name is prepended to the instance name in InsightFinder (forming `device/instance`).

| Field | Description |
|---|---|
| `device_map_table` | Lookup table name |
| `device_map_id_field` | Column in the lookup table that holds the raw ID |
| `device_map_name_field` | Column in the lookup table that holds the display name |

**All three must be set together, or leave all three empty.**

#### Example

Suppose each server belongs to a datacenter stored as a numeric `dc_id`:

```
server_metrics
┌──────────────────────────────────────────────────────────────┐
│ ts                  │ server_id │ dc_id │ cpu_pct │ mem_pct  │
│ 2025-01-15 10:00:00 │ 42        │ 7     │ 78.3    │ 55.1     │
└──────────────────────────────────────────────────────────────┘
```

Lookup table `datacenter_registry`:

```
datacenter_registry
┌──────────────────────┐
│ id  │ dc_name        │
│ 7   │ us-east-1      │
└──────────────────────┘
```

Configure:

```ini
instance_field     = server_id
instance_map_table = host_registry
instance_map_id_field   = id
instance_map_name_field = hostname

device_field       = dc_id
device_map_table   = datacenter_registry
device_map_id_field   = id
device_map_name_field = dc_name
```

Result: InsightFinder receives the instance as `us-east-1/web-prod-01.example.com`.

---

### `[mssql]` — Streaming and Replay

| Field | Description |
|---|---|
| `query_window` | Minutes to look back on each run. Default: `10` |
| `hist_time_range` | Replay a fixed time range instead of streaming live. Format: `2024-01-01 00:00:00,2024-01-02 00:00:00` |
| `hist_batch_interval` | Chunk size for replay, in seconds. Required when `hist_time_range` is set. Example: `3600` |

**Streaming (live):** leave `hist_time_range` empty. The agent runs on a schedule and queries the most recent `query_window` minutes of data each time.

**Replay (history):** set both `hist_time_range` and `hist_batch_interval`. The agent walks through the entire range in batches.

---

### `[insightfinder]` — InsightFinder Connection

| Field | Required | Default | Description |
|---|---|---|---|
| `user_name` | Yes | — | Your InsightFinder username |
| `license_key` | Yes | — | API license key from Account Profile |
| `project_name` | Yes | — | Project name created in InsightFinder UI |
| `project_type` | Yes | `metric` | `metric` or `log` |
| `sampling_interval` | Yes | `1` | Data collection frequency in minutes. Append `s` for seconds (e.g. `30s`) |
| `chunk_size_kb` | No | `2048` | Max HTTP payload size in KB |
| `if_url` | No | `https://app.insightfinder.com` | InsightFinder URL |
| `if_http_proxy` | No | — | HTTP proxy for InsightFinder connection |
| `if_https_proxy` | No | — | HTTPS proxy for InsightFinder connection |
| `containerize` | No | — | Set to `true` if the agent runs inside a container |

---

## Complete Example: Metric Config

```ini
[mssql]

host     = sql-server.example.com
user     = insight_reader
password = s3cr3t
database = OpsDB
port     = 1433

table_list = server_metrics

instance_map_table      = host_registry
instance_map_id_field   = id
instance_map_name_field = hostname

device_map_table      = datacenter_registry
device_map_id_field   = id
device_map_name_field = dc_name

sql = """
      SELECT *
      FROM {{table}}
      WHERE {{timestamp_field}} >= '{{start_time}}' AND {{timestamp_field}} < '{{end_time}}';
      """

data_format = json
timestamp_field  = ts
timestamp_format = YYYY-MM-DD HH:mm:ss.SSSSSSS
timezone         = UTC
target_timestamp_timezone = UTC

instance_field = server_id
device_field   = dc_id
data_fields    = cpu_pct,mem_pct,disk_read,disk_write,net_in,net_out

query_window = 10

[insightfinder]

user_name    = your_username
license_key  = your_license_key
project_name = my-mssql-metrics
project_type = metric
sampling_interval = 1
if_url = https://app.insightfinder.com
```

---

## Complete Example: Log Config

```ini
[mssql]

host     = sql-server.example.com
user     = insight_reader
password = s3cr3t
database = OpsDB
port     = 1433

table_list = app_logs

instance_map_table      = host_registry
instance_map_id_field   = id
instance_map_name_field = hostname

device_map_table =
device_map_id_field =
device_map_name_field =

sql = """
      SELECT *
      FROM {{table}}
      WHERE {{timestamp_field}} >= '{{start_time}}' AND {{timestamp_field}} < '{{end_time}}';
      """

data_format = json
timestamp_field  = ts
timestamp_format = YYYY-MM-DD HH:mm:ss.SSSSSSS
timezone         = UTC
target_timestamp_timezone = UTC

instance_field = host
data_fields    =

query_window = 10

[insightfinder]

user_name    = your_username
license_key  = your_license_key
project_name = my-mssql-logs
project_type = log
sampling_interval = 1
if_url = https://app.insightfinder.com
```
