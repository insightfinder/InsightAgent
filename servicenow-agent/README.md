# ServiceNow Agent
Queries ServiceNow (Table API) for ticket data -- incidents, change requests, problems, or any other table -- across one or more named queries, and sends each record to InsightFinder as a LOG entry.

## Quick Start with Docker

1. **Configure the agent:**
   ```bash
   cp conf.d/config.ini.template conf.d/config.ini
   # Edit conf.d/config.ini with your ServiceNow and InsightFinder settings
   ```

2. **Set credentials:**
   ```bash
   cp example.env .env
   # Edit .env with your ServiceNow credentials -- see "Credentials (.env)" below.
   # .env is never baked into the image or committed (see .gitignore/.dockerignore).
   ```

3. **Build the Docker image:**
   ```bash
   docker build -t servicenow-agent .
   ```

4. **Run the container:**
   ```bash
   docker run -d \
     --name servicenow-agent \
     -v $(pwd)/conf.d:/app/conf.d:ro \
     -v $(pwd)/.env:/app/.env:ro \
     -v $(pwd)/cache:/app/cache \
     -v $(pwd)/logs:/app/logs \
     servicenow-agent
   ```
   `.env` is mounted as a file, the same way `conf.d` is -- the agent reads it from its own directory on startup, so there's nothing Docker-specific to remember. (Real environment variables set on the container, e.g. via `-e`/`--env-file`/a secrets manager, work too and always take priority over the file -- use whichever fits your deployment.)

5. **Monitor the agent:**
   ```bash
   docker logs -f servicenow-agent
   tail -f logs/*.log
   ```

6. **Stop/restart:**
   ```bash
   docker stop servicenow-agent
   docker start servicenow-agent
   docker restart servicenow-agent
   ```

### Docker Volume Mounts

- **`/app/conf.d`** - Configuration directory (required), mounted read-only.
- **`/app/.env`** - ServiceNow credentials (required unless supplied as real container env vars instead), mounted read-only. Picked up automatically -- no flag needed beyond the mount itself.
- **`/app/cache`** - **Required and must be writable.** Holds the OAuth token cache. Losing this volume just costs one extra token fetch on the next run -- it does not affect what data gets queried.
- **`/app/logs`** - Log output directory (optional but recommended).

### Docker Advanced Usage

**Custom cron parameters:**
```bash
docker run -d \
  --name servicenow-agent \
  -v $(pwd)/conf.d:/app/conf.d:ro \
  -v $(pwd)/.env:/app/.env:ro \
  -v $(pwd)/cache:/app/cache \
  -v $(pwd)/logs:/app/logs \
  servicenow-agent \
  /bin/bash -c "python3 cron.py -v -p 8 -o 15"
```

**Docker Compose:**
```yaml
version: '3.8'
services:
  servicenow-agent:
    build: .
    container_name: servicenow-agent
    volumes:
      - ./conf.d:/app/conf.d:ro
      - ./.env:/app/.env:ro
      - ./cache:/app/cache
      - ./logs:/app/logs
    restart: unless-stopped
    environment:
      - TZ=UTC
```

## Local Installation

### Prerequisites
- Python 3.6+ (Python 3.13 recommended)
- pip3

### Installation Steps

1. **Setup Python environment:**
   ```bash
   ./setup/configure_python.sh
   ```

2. **Configure the agent:**
   ```bash
   cp conf.d/config.ini.template conf.d/config.ini
   # Edit conf.d/config.ini
   ```

3. **Set credentials:**
   ```bash
   cp example.env .env
   # Edit .env with your ServiceNow credentials -- see "Credentials (.env)" below.
   ```
   `configure_python.sh` (step 1) already did this for you if `.env` didn't exist yet.

4. **Verify OAuth by hand before touching the agent.** The agent always uses the password grant against `/oauth_token.do` (not configurable -- see below):
   ```bash
   curl -s -X POST 'https://your-instance.service-now.com/oauth_token.do' \
     -d 'grant_type=password' -d 'client_id=YOUR_CLIENT_ID' -d 'client_secret=YOUR_CLIENT_SECRET' \
     -d 'username=YOUR_USER' -d 'password=YOUR_PASSWORD'
   ```
   A successful response is `{"access_token": ..., "refresh_token": ..., "expires_in": 1800, ...}`.

5. **Test the configuration (recommended):**
   ```bash
   ./setup/test_agent.sh
   ```
   This queries ServiceNow but does not send data to InsightFinder.

   To inspect the exact schema of what would be sent (e.g. to check field names before writing `data_fields`), add `--dump-file`:
   ```bash
   venv/bin/python3 getmessages_servicenow.py -t --dump-file /tmp/if_dump.jsonl
   cat /tmp/if_dump.jsonl | python3 -m json.tool
   ```
   Each line is one `{eventId, tag, data}` object exactly as it would be POSTed to InsightFinder. The file is truncated at the start of each run. Combine with `-t` to inspect without actually sending; without `-t`, the same entries are both dumped to the file and sent for real.

6. **Run the agent:**
   ```bash
   nohup venv/bin/python3 cron.py &
   ```

7. **Stop the agent:**
   ```bash
   jobs -l
   kill -9 <PID>
   ```

## Configuration

`conf.d/config.ini` has a `[servicenow]` section (connection settings and defaults shared by every query), one or more `[query:NAME]` sections (one per ServiceNow query), and the `[insightfinder]` section. Credentials are never in `config.ini` -- see "Credentials (.env)" below.

### Quick Configuration Example

```ini
[servicenow]
base_url = https://acme.service-now.com
auth_type = oauth2

[query:P1P2_Incidents]
table = incident
sysparm_query = active=true^priority<=2
data_fields = sys_id,number,short_description,priority,cmdb_ci.name,assignment_group.name
instance_field = cmdb_ci.name,assignment_group.name
default_instance_name = servicenow-incident

[insightfinder]
user_name = your_email@example.com
license_key = your_license_key
project_name = my-servicenow-tickets
project_type = log
sampling_interval = 5
run_interval = 5
```

### Multiple Queries

Add one `[query:NAME]` section per query. `NAME` must be unique across the config and is attached to every record as `data._query`. Comment out a section (or clear its `table` line) to disable a query without deleting it. Each section overrides `[servicenow]`'s defaults for any key it sets; keys it doesn't set fall back to `[servicenow]`.

A query's tickets go to the `[insightfinder]` section's `project_name` unless the query sets its own `project_name`, in which case that project is auto-created if it doesn't already exist.

### Credentials (`.env`)

ServiceNow credentials are never read from `config.ini` -- only from the environment, so a config file can be shared or committed without exposing secrets. Copy `example.env` to `.env` and fill in the block that matches `[servicenow] auth_type`:

```bash
## auth_type = oauth2 (password grant against /oauth_token.do -- fixed, not configurable)
SERVICENOW_OAUTH_CLIENT_ID=
SERVICENOW_OAUTH_CLIENT_SECRET=
SERVICENOW_OAUTH_USERNAME=
SERVICENOW_OAUTH_PASSWORD=

## auth_type = basic
SERVICENOW_USERNAME=
SERVICENOW_PASSWORD=
```

At startup the agent loads `<agent_dir>/.env` into its own process automatically -- there's nothing to pass on the command line, in `agent.txt`, or in `cron.py`. Real environment variables (set by the shell, `docker run -e`, `--env-file`, a secrets manager, etc.) are checked first and always take priority over the file, so `.env` is just a convenience default for local/dev use, not the only way to supply credentials. `.env` is excluded from git (`.gitignore`) and from the Docker build context (`.dockerignore`) -- for Docker, mount it as a file (see "Docker Volume Mounts" above) or inject real container env vars instead.

The agent never logs a credential value or a raw token-endpoint request/response body -- only the HTTP status code and, on failure, ServiceNow's `error_description`.

### Config Variables

#### `[servicenow]` -- Connection

* **`base_url`** (Required) -- Instance base URL, no trailing path. Example: `https://acme.service-now.com`

* **`auth_type`** (Optional) -- `oauth2` (default) or `basic`. Determines which `.env` variables are required -- see "Credentials (.env)" above. `oauth2` always uses the password grant against `/oauth_token.do`, with no scope -- neither is configurable, since that's the only combination that works against a real instance without extra ServiceNow-side setup.

* **`verify_certs`** (Optional) -- `true` (default) or `false`.

* **`ca_certs`** (Optional) -- path to a CA bundle.

* **`agent_http_proxy`** / **`agent_https_proxy`** (Optional)

* **`query_chunk_size`** (Optional) -- records per page (`sysparm_limit`). Default: `1000`.

* **`query_time_offset_seconds`** (Optional) -- backs the window's upper bound off by this much, to absorb clock skew between this host and the ServiceNow instance. Default: `30`.

* **`his_time_range`** (Optional) -- replay a fixed range instead of the live `sampling_interval`-sized window. Format: `YYYY-MM-DD HH:MM:SS,YYYY-MM-DD HH:MM:SS`.

#### `[servicenow]` and `[query:NAME]` -- Defaults inherited per query

Any of these set in `[servicenow]` become the default for every `[query:NAME]` section; setting the same key inside a `[query:NAME]` section overrides it for that query only.

* **`table`** (Required, query-only) -- the ServiceNow table, e.g. `incident`, `em_alert`.

* **`sysparm_query`** (Optional) -- an encoded ServiceNow query, written literally (`%` and `^` need no escaping). **Do not** add your own timestamp filter or `ORDERBY` -- the agent appends both automatically, with a total order (`^ORDERBY<timestamp_field>^ORDERBYsys_id`) that's what makes offset paging safe: any record touched mid-pagination gets pushed past the window's upper bound and drops out of the result set, rather than shifting into an already-fetched page.

* **`data_fields`** (Optional) -- comma-separated ServiceNow fields. Doubles as the wire projection (`sysparm_fields`) *and* the output selection, so narrowing it also shrinks the response. Dot-walk reference fields to pull a related record's column in the same request, e.g. `cmdb_ci.name`, `assignment_group.name`. **Leave blank to fetch and send every field on the record** -- useful for discovery, but a wide table like `incident` has ~180 columns; set this explicitly for production.

* **`timestamp_field`** (Optional) -- Default: `sys_created_on`. Use `sys_updated_on` instead if a ticket's later edits (state changes, resolution, etc.) should also re-surface it in the query window -- note that also makes the same ticket appear multiple times as its data changes, since each edit produces a new log entry for it.

* **`timestamp_format`** (Optional) -- [arrow](https://arrow.readthedocs.io/en/latest/#supported-tokens) format string. Default: `YYYY-MM-DD HH:mm:ss` (ServiceNow's internal format).

* **`timezone`** (Optional) -- timezone the raw timestamp value is in, as per pytz. Default: `UTC`. The agent always reads the `.value` of a timestamp field (ServiceNow's UTC internal representation), never `.display_value` (rendered in the integration user's locale), so this normally stays `UTC`.

* **`target_timestamp_timezone`** (Optional) -- timezone the timestamp is stored as in InsightFinder. Default: `UTC`.

* **`instance_field`** (Optional) -- comma-separated priority list of fields; the first non-empty value becomes the ticket's InsightFinder instance name (`tag`). Fields returned via a reference lookup keep their dotted name -- use `cmdb_ci.name` literally, not nested syntax. Putting the affected CI first (`cmdb_ci.name`) lines tickets up with the instance names already used by the customer's metric/log projects for that asset; `business_service.name` and `assignment_group.name` are good fallbacks for tickets with no CI attached.

* **`instance_field_regex`** (Optional) -- extract the instance from a field via regex. Syntax: `<field1>::<regex1>,<field2>::<regex2>`.

* **`instance_whitelist`** (Optional) -- regex; instances not matching are dropped. Use this to bound cardinality if `cmdb_ci.name` on a large instance would otherwise mint thousands of InsightFinder instances.

* **`default_instance_name`** (Optional) -- used when no `instance_field` value is found.

* **`project_name`** (Optional, query-only) -- sends this query's tickets to a different InsightFinder project (auto-created), instead of `[insightfinder] project_name`.

**Not supported: `component_field`.** In LOG mode, InsightFinder's log entry shape is `{eventId, tag, data}` -- there is no `componentName` field, so a `component_field` setting would silently do nothing. Carry ownership/team context inside `data` instead (e.g. via `assignment_group.name` in `data_fields`).

#### `[insightfinder]`

Same as every other InsightFinder collector agent in this repo: `user_name`, `license_key`, `token`, `project_name`, `system_name`, `project_type` (must be `log` or `logreplay` for this agent), `containerize`, `enable_holistic_model`, `sampling_interval`, `frequency_sampling_interval`, `log_compression_interval`, `enable_log_rotation`, `log_backup_count`, `run_interval`, `worker_timeout`, `chunk_size_kb`, `if_url`, `if_http_proxy`, `if_https_proxy`. See `.CONFIGVARS.md` for details.

## How ticket data becomes a log entry

Each ServiceNow record becomes one InsightFinder LOG entry:

```json
{
  "eventId": "1754562862000",
  "tag": "web-prod-01.acme.com",
  "data": {
    "_query": "P1P2_Incidents", "_table": "incident",
    "sys_id": "9c573169c611228700193229fff72400", "number": "INC0000055",
    "short_description": "SAP Sales app is not accessible",
    "priority": "1 - Critical", "cmdb_ci.name": "web-prod-01.acme.com",
    "assignment_group.name": "Software"
  }
}
```

- `eventId` is the record's `timestamp_field` (default `sys_created_on`), in epoch milliseconds.
- `tag` is the instance name derived from `instance_field`.
- `data` is either the selected `data_fields`, or (if blank) the entire record, always with `_query`, `_table`, `sys_id`, and `number` added.

**Time window: stateless, config-driven.** Every run queries exactly the last `sampling_interval` seconds back from now (offset by `query_time_offset_seconds`) for every query -- nothing is persisted across runs, so the agent always does exactly what `config.ini` says regardless of when it last ran. This means **`run_interval` and `sampling_interval` should match** -- if cron fires every 5 minutes (`run_interval = 5`) but `sampling_interval = 1`, you'll miss 4 out of every 5 minutes of tickets; if `sampling_interval` is larger than `run_interval`, consecutive runs' windows overlap and the same ticket is sent more than once. `query_time_offset_seconds` exists to absorb clock skew, not to compensate for a mismatched interval.

Within a single run, an in-memory set of `(query, sys_id, timestamp)` guards against duplicate records from overlapping pages of the same request. `sys_id` and the timestamp field are always present in `data`, so a duplicate crossing a run boundary (from overlapping `sampling_interval`/`run_interval` values, or from re-running manually) is at least identifiable downstream.

## Troubleshooting

### Docker
```bash
docker ps -a | grep servicenow-agent
docker logs --tail 100 servicenow-agent
docker exec -it servicenow-agent /bin/bash
docker exec -it servicenow-agent python3 getmessages_servicenow.py -t
```

### Local Installation
```bash
ps aux | grep cron.py
tail -100 logs/*.log
./setup/test_agent.sh
venv/bin/python3 cron.py -v
```

### Common Issues

**A hibernating developer instance returns no data / a parse error.** ServiceNow Personal Developer Instances hibernate after inactivity and respond to any request with HTTP 200 and an HTML "Instance Hibernating" page instead of JSON. Log in via the browser to wake it, then re-run.

**Every run re-sends the same tickets, or misses some.** There's no persisted state between runs by design -- each run queries exactly the last `sampling_interval` seconds. Overlapping/repeated data means `sampling_interval` is larger than the actual gap between runs (e.g. cron's `run_interval` is shorter, or you're re-running manually more often than `sampling_interval` covers); missed data means the reverse. Set `run_interval == sampling_interval`.

**One query 403s but the others still work.** Expected -- each query runs and fails independently, and a table the integration user lacks read access to doesn't block the rest. Check the ServiceNow integration user's ACLs for that specific table.

**No data in InsightFinder for a specific query:**
- Check the agent log for that query's `X-Total-Count=` line -- if it's 0, the `sysparm_query` + time window genuinely matched nothing.
- Confirm `timestamp_field` exists on that table (some tables don't have `sys_created_on` populated the way `incident` does).
- Verify `license_key` and `project_name` (or the query's `project_name` override) are correct.

**OAuth token errors / "environment variable" config errors:**
- Confirm `.env` exists in the agent directory (or the equivalent real env vars are set) and has the variables matching `auth_type` -- see "Credentials (.env)" above. In Docker, confirm `.env` is actually mounted at `/app/.env`.
- Re-run the `curl` verification from step 4 above with the exact same client ID and credentials as `.env`.
- The agent never logs the client secret or password, or the raw token endpoint response -- check for an `error_description` in the log line instead.

**Permission errors (Docker):**
- Container runs as user `1001`. Adjust ownership if needed:
  ```bash
  sudo chown -R 1001:1001 conf.d cache logs
  ```
