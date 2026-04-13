# Datadog Trace Agent for InsightFinder

Streams distributed trace spans from Datadog to InsightFinder in real time. The agent queries the Datadog Spans Search API on a recurring schedule, transforms the results into InsightFinder's log-streaming format, and sends them in batches.

---

## How It Works

```
conf.d/config.yaml
       ↓
  main.py reads config
       ↓
  Query Datadog Spans Search API (v2)
       ↓
  Transform spans → InsightFinder log entries
       ↓
  POST to InsightFinder
```
---

## Requirements

- Python 3.7+
- `pyyaml >= 6.0`

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Configuration

Copy and edit the template:

```bash
cp conf.d/config.yaml conf.d/my-config.yaml
```

The agent loads **all** `.yaml` files from the `conf.d/` directory, so you can maintain one file per data source.

### `conf.d/config.yaml`

```yaml
datadog:
  # Base URL of your Datadog site.
  # US1 (default): https://api.datadoghq.com
  # EU:            https://api.datadoghq.eu
  # US3:           https://us3.datadoghq.com
  # US5:           https://us5.datadoghq.com
  endpoint: "https://api.datadoghq.com"

  # Datadog API key (Organization Settings → API Keys)
  api_key: "<YOUR_API_KEY>"

  # Datadog Application key (Organization Settings → Application Keys)
  application_key: "<YOUR_APP_KEY>"

  trace:
    # One entry per group of spans to collect.
    # Each entry is a separate query; filter expressions are ANDed together.
    - query:
        - "service:<name>"        # filter by service
        - "env:<name>"            # filter by environment
        - "status:error"          # only error spans
        - "@http.status_code:500" # filter on a span tag
      # Span field used as the InsightFinder instance/host identifier.
      # Common values: "service", "resource_name", or any span attribute.
      instance_name_field: "service"

insightfinder:
  # Full URL of your InsightFinder instance
  url: "https://app.insightfinder.com"

  # InsightFinder account username
  username: "<YOUR_USERNAME>"

  # InsightFinder license key (Account Settings)
  license_key: "<YOUR_LICENSE_KEY>"

  # Target project name in InsightFinder
  project: "<YOUR_PROJECT_NAME>"

agent:
  # Minutes to look back from "now" each run.
  # Set this equal to (or slightly larger than) your cron interval to avoid gaps.
  lookback: 1

  # Maximum spans to fetch per query per run.
  limit: 2000
```

### Datadog Query Syntax

The `query` list supports any [Datadog search syntax](https://docs.datadoghq.com/tracing/trace_explorer/query_syntax/):

| Filter | Example |
|---|---|
| Service | `service:payment-service` |
| Environment | `env:production` |
| Status | `status:error` |
| Span tag | `@http.status_code:500` |
| Resource | `resource_name:"/checkout"` |

Leave `query` empty (or omit it) to collect all spans.

---

## Running

### Manually

```bash
source .venv/bin/activate
python main.py
```

### On a Cron Schedule

Add to your crontab to run every minute:

```
* * * * * /path/to/datadog-trace/.venv/bin/python /path/to/datadog-trace/main.py >> /var/log/datadog-trace.log 2>&1
```

Set `agent.lookback` to match your cron interval so there are no gaps between runs.

---

## Project Structure

```
datadog-trace/
├── main.py            # Entry point — config loading, Datadog querying, data transformation
├── insightfinder.py   # InsightFinder API client
├── requirements.txt   # Python dependencies
└── conf.d/
    └── config.yaml    # Configuration template
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| No spans forwarded | Verify `api_key` / `application_key` and that the `query` filters match existing spans |
| HTTP 401 from InsightFinder | Verify `username` and `license_key` |
| HTTP 403 from Datadog | Ensure the Application Key has `apm_read` scope |
| Gaps in data | Increase `agent.lookback` to slightly exceed the cron interval |
| Too many spans | Reduce `limit` or narrow the `query` filters |
