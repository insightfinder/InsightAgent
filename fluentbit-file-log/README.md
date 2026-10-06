# Fluent Bit → InsightFinder (local log files)

Tails local log files with [Fluent Bit](https://fluentbit.io) and streams each line to an
InsightFinder log project. No extra agent or relay is needed: a Lua filter builds the same
payload the Go agents (e.g. `kubernetes-agent`) send to `/api/v1/customprojectrawdata`.

## Files

| File | Purpose |
| --- | --- |
| `fluent-bit.conf` | Pipeline: `tail` input → Lua filter → `http` output |
| `insightfinder.lua` | Converts records to InsightFinder's JSON payload and batches them |
| `parsers.conf` | Optional parsers (e.g. `json`) for structured log lines |

## How it works

```
log file ──tail──▶ lua filter (buffer + build JSON) ──http──▶ InsightFinder
dummy (1/s tick) ─┘   flushes partial batches                /api/v1/customprojectrawdata
```

Each request body looks like:

```json
{
  "userName": "...", "licenseKey": "...", "projectName": "...", "systemName": "...",
  "agentType": "LogStreaming",
  "metricData": [
    {"timestamp": 1791316229496, "tag": "web01", "componentName": "api", "data": "the log line"}
  ]
}
```

with headers `Content-Type: application/json` and `agent-type: Stream`.

- `timestamp` is the Fluent Bit record time in epoch milliseconds (read time, or the time
  parsed from the line if you use a parser with `Time_Key`).
- `tag` is the InsightFinder **instance name**; `componentName` is the component.
- `data` is the raw line. If you enable a parser, `data` is the parsed JSON object instead.

A batch is sent when it reaches `IF_BATCH_SIZE` lines or `IF_BATCH_BYTES` bytes, or when its
oldest line is `IF_FLUSH_INTERVAL` seconds old.

## 1. Create the log project

Fluent Bit cannot create projects. Create a **Log** project in the InsightFinder UI, or run:

```bash
curl -X POST "https://$IF_HOST/api/v1/check-and-add-custom-project" \
  --data-urlencode operation=create \
  --data-urlencode userName="$IF_USER_NAME" \
  --data-urlencode licenseKey="$IF_LICENSE_KEY" \
  --data-urlencode projectName="$IF_PROJECT_NAME" \
  --data-urlencode systemName="$IF_SYSTEM_NAME" \
  --data-urlencode instanceType=OnPremise \
  --data-urlencode projectCloudType=OnPremise \
  --data-urlencode dataType=Log \
  --data-urlencode insightAgentType=Custom \
  --data-urlencode samplingInterval=60
```

## 2. Configure

Settings are environment variables.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `IF_HOST` | yes | | InsightFinder host, e.g. `app.insightfinder.com` (no scheme) |
| `IF_USER_NAME` | yes | | InsightFinder user name |
| `IF_LICENSE_KEY` | yes | | InsightFinder license key |
| `IF_PROJECT_NAME` | yes | | Log project name |
| `LOG_PATH` | yes | | File(s) to tail; globs allowed, comma-separated for several |
| `IF_SYSTEM_NAME` | no | empty | System the project belongs to |
| `IF_INSTANCE_NAME` | no | short hostname | Instance name for every line |
| `IF_INSTANCE_FIELD` | no | | Take the instance name from this record field instead (needs a parser) |
| `IF_COMPONENT_NAME` | no | empty | Component name for every line |
| `IF_COMPONENT_FIELD` | no | | Take the component name from this record field instead (needs a parser) |
| `IF_MESSAGE_KEY` | no | `log` | Field holding the raw line (`tail` uses `log`) |
| `IF_BATCH_SIZE` | no | `1000` | Max lines per request |
| `IF_BATCH_BYTES` | no | `2000000` | Max payload bytes per request (InsightFinder rejects > 10 MB) |
| `IF_FLUSH_INTERVAL` | no | `5` | Seconds before a partial batch is sent |

Instance and component names are cleaned like the Go agents do (`_` → `.`, `:` → `-`,
brackets, braces, commas and spaces removed).

Settings that rarely change are set directly in `fluent-bit.conf`:

- **Port / TLS**: `443` with TLS on. For an on-prem server over plain HTTP, set `Port` and
  `tls Off` in the `[OUTPUT]` section.
- **`Read_from_Head Off`**: only lines written after the first start are sent. Set `On` to
  also send what is already in the file.
- **`DB`**: file offsets are stored in `/var/lib/fluent-bit/insightfinder-tail.db`, so a
  restart continues where it left off. The directory must exist and be writable.
- **Structured logs**: uncomment `Parser json` (or add your own parser to `parsers.conf`).
  Lines that fail to parse are still sent as plain strings.

## 3. Run

### Docker

```bash
docker run -d --name fluent-bit-insightfinder \
  -v "$PWD":/fluent-bit/etc:ro \
  -v /var/log/myapp:/logs:ro \
  -v fluent-bit-db:/var/lib/fluent-bit \
  -e IF_HOST=app.insightfinder.com \
  -e IF_USER_NAME=myuser \
  -e IF_LICENSE_KEY=xxxxxxxx \
  -e IF_PROJECT_NAME=my-log-project \
  -e IF_SYSTEM_NAME=my-system \
  -e IF_INSTANCE_NAME=web01 \
  -e LOG_PATH='/logs/*.log' \
  fluent/fluent-bit:latest \
  /fluent-bit/bin/fluent-bit -c /fluent-bit/etc/fluent-bit.conf
```

On SELinux hosts (Fedora/RHEL) add `:Z` to the bind mounts.

### Installed Fluent Bit (systemd)

```bash
sudo mkdir -p /etc/fluent-bit/insightfinder /var/lib/fluent-bit
sudo cp fluent-bit.conf insightfinder.lua parsers.conf /etc/fluent-bit/insightfinder/

# Point the service at this config and give it the settings
sudo systemctl edit fluent-bit
#   [Service]
#   Environment=IF_HOST=app.insightfinder.com IF_USER_NAME=myuser IF_LICENSE_KEY=xxxxxxxx
#   Environment=IF_PROJECT_NAME=my-log-project LOG_PATH=/var/log/myapp/*.log
#   ExecStart=
#   ExecStart=/opt/fluent-bit/bin/fluent-bit -c /etc/fluent-bit/insightfinder/fluent-bit.conf

sudo systemctl restart fluent-bit
```

## Verify

Fluent Bit logs one line per request:

```
[output:http:http.0] app.insightfinder.com:443, HTTP status=200
{"success":true, ...}
```

Non-2xx responses are retried up to 5 times (`Retry_Limit`). Then check the project in the
InsightFinder UI.

## Notes

- Lines buffered in the Lua filter but not yet sent (at most `IF_FLUSH_INTERVAL` seconds'
  worth) are lost if Fluent Bit stops, because their offsets are already in the DB.
- A failed request is retried with the whole Fluent Bit chunk, so a partial failure can send
  some lines twice.
- Fluent Bit's `http` output only checks the HTTP status. A `200` with `"success": false`
  in the body (for example, a wrong project name) is logged but not retried.
- Needs an `http` output that supports `body_key` / `headers_key`. Tested with Fluent Bit 5.1.3.
