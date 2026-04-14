# Splunk Agent

Streams log events from **Splunk Enterprise or Splunk Cloud** to **InsightFinder**.

- Two operation modes: **continuous** (live polling) and **historical** (download to JSONL files)
- Polls Splunk via its REST API on a configurable interval
- Supports multiple independent SPL queries
- Forwards the **full Splunk event as structured JSON** (all fields — `_raw`, `_time`, `host`, `source`, `sourcetype`, `index`, and any extras)
- Configurable tag (instance name) and component name mapping — use any Splunk field or a fixed value
- Optional concurrent query execution

---

## Requirements

| Tool | Version |
|------|---------|
| Go   | 1.21+   |
| Splunk Enterprise | 8.x / 9.x |
| Splunk Cloud | any |

---

## Project structure

```
splunk-agent/
├── configs/
│   ├── config.yaml      ← all configuration (edit this)
│   ├── config.go        ← YAML loader + validation
│   └── type.go          ← config structs
├── splunk/
│   ├── splunk.go        ← Splunk REST API client
│   └── type.go          ← Splunk response types
├── insightfinder/
│   ├── insightfinder.go ← IF project management + log sender
│   ├── type.go          ← IF types
│   └── util.go          ← CleanDeviceName helper
├── worker/
│   └── worker.go        ← continuous polling loop
├── main.go              ← entrypoint
├── go.mod
└── go.sum
```

---

## Setup

### 1. Clone / download the agent

```bash
git clone <repo-url>
cd splunk-agent
```

### 2. Install Go dependencies

```bash
go mod tidy
```

### 3. Configure the agent

Edit **`configs/config.yaml`**. The three sections are:

#### `agent` — general settings

```yaml
agent:
  log_level: "INFO"    # DEBUG | INFO | WARN | ERROR
  mode: "continuous"   # "continuous" | "historical"
```

Two modes are supported:

| Mode | Description |
|------|-------------|
| `continuous` | Poll Splunk every `sampling_interval` seconds and forward events to InsightFinder indefinitely |
| `historical` | Query a fixed time range, write results to JSONL files on disk, then exit |

**Historical mode** does not require InsightFinder credentials — it only connects to Splunk.

```yaml
agent:
  mode: "historical"
  start_time:     "2024-01-01T00:00:00Z"   # RFC3339 or date-only "2024-01-01"
  end_time:       "2024-01-31T00:00:00Z"   # optional — defaults to now if omitted
  download_path:  "./splunk_downloads"     # directory where JSONL files are saved
  chunk_interval: 60                       # minutes per Splunk job (default 60 = 1 hour)
```

One JSONL file is written per enabled query:

```
splunk_downloads/
  app_logs_1704067200_1706745600.jsonl
  system_errors_1704067200_1706745600.jsonl
```

Each line in a JSONL file is a JSON-encoded log entry with the same structure sent to InsightFinder (`timestamp`, `tag`, `componentName`, `data`). The time range is walked in `sampling_interval`-sized chunks so Splunk is never asked for more than one interval at a time.

#### `splunk` — connection and queries

```yaml
splunk:
  server_url: "https://localhost:8089"   # management port (not 8000)

  # Splunk Enterprise — basic auth
  username: "admin"
  password: "yourpassword"
  token: ""

  # Splunk Cloud — token auth (generate in UI: Settings → Tokens → New Token)
  # Leave username + password empty when using a token.
  # server_url: "https://<your-stack>.splunkcloud.com:8089"
  # token: "eyJra..."

  verify_ssl: false      # set true for Splunk Cloud (has a valid cert)
  query_timeout: 60      # seconds to wait for each search job to finish
  max_results: 5000      # max events returned per query per interval

  # Run queries concurrently instead of one at a time.
  # max_concurrent limits parallelism (0 = no cap, all at once).
  concurrent_queries: false
  max_concurrent:     0

  queries:
    - name:    "app_logs"
      query:   "search index=main sourcetype=app-logs"
      enabled: true

    - name:    "errors"
      query:   "search index=main (ERROR OR FATAL)"
      enabled: true
      max_results: 1000   # optional per-query override

      # Per-query field mapping overrides (see Field Mapping section below)
      # instance_field:  "host"
      # instance_value:  ""
      # component_field: "index"
      # component_value: ""
```

> **Time modifiers** (`earliest`, `latest`) are **not** required in the SPL.
> The agent automatically appends `earliest_time` and `latest_time` to every
> search job based on the last successful poll window.

#### `insightfinder` — project and HTTP settings

```yaml
insightfinder:
  server_url:  "https://app.insightfinder.com"
  username:    "your-if-username"
  license_key: "your-license-key"

  logs_project_name: "splunk-logs"    # created automatically if it doesn't exist
  logs_system_name:  "splunk-system"
  logs_project_type: "LOG"

  sampling_interval: 60   # seconds between Splunk polls

  cloud_type:    "OnPremise"   # OnPremise | AWS | Azure | GCP
  instance_type: "OnPremise"
  is_container:  false

  retry_times:    3
  retry_interval: 5    # seconds between retries on failure

  # Global field mapping (see Field Mapping section below)
  instance_field:  "host"
  instance_value:  ""
  component_field: "sourcetype"
  component_value: ""
```

---

## Field mapping

Each Splunk event is forwarded to InsightFinder as a **structured JSON object** containing all fields returned by Splunk. The agent also resolves two special InsightFinder fields from those event fields:

| InsightFinder field | Default Splunk source | Description |
|---|---|---|
| Instance name | `host` | The machine / device that produced the log |
| `componentName` | `sourcetype` | The log type or application |
| `data` | full event JSON | All Splunk fields as a JSON object |
| `timestamp` | `_time` | Event time in milliseconds |

### Resolution order

The instance name and component are resolved using the following priority chain (first non-empty value wins):

```
1. query.instance_value  — fixed string, per query
2. query.instance_field  — Splunk field name, per query
3. insightfinder.instance_value  — fixed string, global
4. insightfinder.instance_field  — Splunk field name, global  (default: "host")
```

The same chain applies for `component_value` / `component_field` (default field: `"sourcetype"`).

### Examples

**Use a different Splunk field as the instance name (globally)**

```yaml
insightfinder:
  instance_field: "source"      # use the Splunk source field instead of host
  component_field: "index"      # use the index as componentName
```

**Use a fixed instance name for all events in one query**

```yaml
splunk:
  queries:
    - name: "firewall_logs"
      query: "search index=network sourcetype=cisco:asa"
      enabled: true
      instance_value: "firewall"     # every event gets instance="firewall"
      component_field: "sourcetype"  # still dynamic for component
```

**Use a custom Splunk field (e.g. a field your transforms.conf extracts)**

```yaml
insightfinder:
  instance_field:  "device_id"   # any field Splunk returns works — not hardcoded
  component_field: "app_name"
```

---

## Concurrent queries

By default, queries run sequentially. To dispatch all enabled queries to Splunk in parallel:

```yaml
splunk:
  concurrent_queries: true
  max_concurrent: 0    # 0 = all at once; e.g. 3 = max 3 running simultaneously
```

Each query tracks its own time window independently, so a slow or failed query never blocks others (even in sequential mode).

---

## Splunk setup

### Splunk Enterprise

The agent connects to the **management API port** (default `8089`), not the web UI port (`8000`).

Make sure the Splunk user has the `search` capability (the built-in `user` role is sufficient for searching).

Verify the management port is reachable:

```bash
curl -k -u admin:password https://localhost:8089/services/server/info?output_mode=json
```

### Splunk Cloud

1. Obtain your stack URL (e.g. `https://mystack.splunkcloud.com:8089`)
2. Create a token: **Settings → Tokens → New Token**
3. Set in `config.yaml`:
   ```yaml
   splunk:
     server_url: "https://mystack.splunkcloud.com:8089"
     token: "<paste token here>"
     username: ""
     password: ""
     verify_ssl: true
   ```

---

## InsightFinder setup

1. Log in to your InsightFinder instance
2. The agent **auto-creates the project** on first run if it does not exist
3. After the first successful poll, events appear under the configured project name

---

## Build and run

```bash
# Build binary
go build -o splunk-agent .

# Run
./splunk-agent
```

Or run directly without building:

```bash
go run .
```

The agent runs continuously and logs to stdout. Send `SIGINT` (`Ctrl+C`) or `SIGTERM` to stop gracefully.

---

## How the polling loop works

```
on startup and every sampling_interval seconds:
  for each enabled query (sequential or concurrent):
    start = end of last successful poll  (first run: now - sampling_interval)
    end   = now

    POST /services/search/jobs
         search=<SPL>  earliest_time=<start>  latest_time=<end>

    poll GET /services/search/jobs/<sid>  until isDone=true

    GET /services/search/jobs/<sid>/results?count=<max_results>

    for each event (all Splunk fields captured):
      instance      = CleanDeviceName( resolved via field mapping )
      componentName = CleanDeviceName( resolved via field mapping )
      data          = { full event JSON object }
      timestamp     = _time (ms)

    POST https://app.insightfinder.com/api/v1/customprojectrawdata
         metricData = JSON array of log entries

    advance lastPollTime[query] = end
```

---

## Configuration reference

### `agent`

| Key | Default | Description |
|-----|---------|-------------|
| `log_level` | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `mode` | `continuous` | `continuous` or `historical` |
| `start_time` | — | Start of historical range — RFC3339 or `YYYY-MM-DD`; required for `historical` |
| `end_time` | now | End of historical range — RFC3339 or `YYYY-MM-DD`; defaults to current time |
| `download_path` | — | Directory to write JSONL files; required for `historical` |
| `chunk_interval` | `60` | Minutes per Splunk query chunk in historical mode (larger = fewer jobs, coarser) |

### `splunk`

| Key | Default | Description |
|-----|---------|-------------|
| `server_url` | — | Splunk management URL including port (`:8089`) |
| `username` | — | Basic auth username (Enterprise) |
| `password` | — | Basic auth password (Enterprise) |
| `token` | — | Bearer token (Splunk Cloud) |
| `verify_ssl` | `false` | Verify TLS certificate |
| `max_retries` | `3` | Retry count on HTTP error |
| `query_timeout` | `60` | Seconds to wait for a search job |
| `max_results` | `5000` | Max events per query per interval |
| `concurrent_queries` | `false` | Run all enabled queries in parallel |
| `max_concurrent` | `0` | Max parallel queries (`0` = unlimited); used when `concurrent_queries: true` |

### `splunk.queries[]`

| Key | Default | Description |
|-----|---------|-------------|
| `name` | — | Unique query identifier (used in logs) |
| `query` | — | SPL search string (no time modifiers needed) |
| `enabled` | — | `true` to run, `false` to skip |
| `max_results` | inherits | Override global `max_results` for this query |
| `instance_field` | inherits | Splunk field name to use as IF instance name |
| `instance_value` | — | Fixed string instance name, overrides `instance_field` |
| `component_field` | inherits | Splunk field name to use as IF componentName |
| `component_value` | — | Fixed string component, overrides `component_field` |

### `insightfinder`

| Key | Default | Description |
|-----|---------|-------------|
| `server_url` | `https://app.insightfinder.com` | InsightFinder server URL |
| `username` | — | InsightFinder account username |
| `license_key` | — | InsightFinder license key |
| `logs_project_name` | — | Target project name (auto-created if missing) |
| `logs_system_name` | — | System name for the project |
| `logs_project_type` | `LOG` | Project type |
| `sampling_interval` | `60` | Seconds between Splunk polls |
| `cloud_type` | `OnPremise` | `OnPremise`, `AWS`, `Azure`, `GCP` |
| `instance_type` | `OnPremise` | Instance classification |
| `is_container` | `false` | Set `true` for containerised deployments |
| `chunk_size` | `2097152` | Payload split threshold in bytes (2 MB) |
| `max_packet_size` | `10485760` | Max HTTP payload in bytes (10 MB) |
| `retry_times` | `3` | Retry count on failed IF send |
| `retry_interval` | `5` | Seconds between IF send retries |
| `instance_field` | `host` | Global: Splunk field name → IF instance name |
| `instance_value` | — | Global: fixed string instance name (overrides `instance_field`) |
| `component_field` | `sourcetype` | Global: Splunk field name → IF componentName |
| `component_value` | — | Global: fixed string component (overrides `component_field`) |

---

## Troubleshooting

**`splunk: provide either token or username + password`**
Both authentication fields are empty. Fill in one set in `configs/config.yaml`.

**`create job: unexpected status 401`**
Wrong credentials or token. Verify with:
```bash
curl -k -u admin:password https://localhost:8089/services/search/jobs \
  -d "search=search index=main&output_mode=json"
```

**`create job: unexpected status 403`**
The Splunk user lacks the `search` capability. Grant the `user` role or higher in Splunk.

**`wait job: timed out waiting for job`**
The query is taking longer than `query_timeout`. Increase `splunk.query_timeout` or narrow the SPL.

**No events appear in InsightFinder**
- Set `log_level: "DEBUG"` to see the raw Splunk payload and IF response
- Verify the Splunk query returns events in the Splunk UI (`Search & Reporting` app) for the same time window
