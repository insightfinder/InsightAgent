# Elasticsearch Dataset & Prompt Agent

Queries dataset and prompt indexes from Elasticsearch and uploads them to InsightFinder's LLM Lab. Supports Elasticsearch 7.x and 8.x, and both streaming (live) and historical query modes.

## Overview

The agent reads two types of documents from Elasticsearch:

- **Datasets** — documents with a text `content` field, uploaded to InsightFinder as LLM Lab datasets.
- **Prompt templates** — documents with a list of prompt objects, uploaded as prompt templates. Dataset placeholders in the form `{{dataset_name}}` are automatically resolved to InsightFinder dataset tags.

Duplicate detection is built in: datasets and prompt templates that already exist in InsightFinder are skipped.

## Requirements

Python 3.8+. Install one of the following depending on your Elasticsearch cluster version:

```bash
# Elasticsearch 7.x
pip install "elasticsearch>=7,<8" requests "urllib3>=1.26"

# Elasticsearch 8.x
pip install "elasticsearch>=8" requests "urllib3>=1.26"
```

Or install from `requirements.txt` (defaults to the 7.x client):

```bash
pip install -r requirements.txt
```

## Configuration

Copy the template and fill in your values:

```bash
cp conf.d/config.ini.template conf.d/config.ini
```

### `[elasticsearch]`

| Key | Default | Description |
|-----|---------|-------------|
| `es_uris` | `http://localhost:9200` | Comma-separated Elasticsearch URLs |
| `http_auth` | _(empty)_ | `username:password` for Basic Auth |
| `verify_certs` | `False` | Verify SSL certificates |
| `ca_certs` | _(empty)_ | Path to CA bundle |
| `client_cert` / `client_key` | _(empty)_ | Paths for mutual TLS |
| `timestamp_field` | `@timestamp` | Timestamp field name (dot-notation supported) |
| `query_chunk_size` | `1000` | Documents per pagination page (max 10000) |
| `his_time_range` | _(empty)_ | Historical mode time range (see below) |
| `query_time_offset_seconds` | `0` | Shift query end-time back by N seconds |
| `streaming_lookback_seconds` | `60` | Streaming mode lookback window in seconds |

### `[dataset_index]`

| Key | Default | Description |
|-----|---------|-------------|
| `index` | `test-dataset` | Elasticsearch index name |
| `content_field` | `content` | Field containing dataset text |
| `dataset_name_field` | `dataset_name` | Field containing the dataset name |
| `default_dataset_name` | `default-dataset` | Fallback name when field is absent |

**Expected document schema:**
```json
{ "content": "...", "dataset_name": "my-dataset", "@timestamp": "..." }
```

### `[prompt_index]`

| Key | Default | Description |
|-----|---------|-------------|
| `index` | `test-prompt` | Elasticsearch index name |
| `prompts_field` | `prompts` | Field containing the array of prompt objects |
| `prompt_content_field` | `prompt` | Field within each prompt object holding the text |
| `template_name_field` | `template_name` | Field containing the template name |
| `default_template_name` | `default-template` | Fallback name when field is absent |

**Expected document schema:**
```json
{
  "template_name": "my-template",
  "prompts": [{"prompt": "..."}, {"prompt": "..."}],
  "@timestamp": "..."
}
```

### `[insightfinder]`

| Key | Description |
|-----|-------------|
| `if_url` | InsightFinder base URL (e.g. `https://ai.insightfinder.com`) |
| `user_name` | InsightFinder username |
| `api_key` | InsightFinder API key |

## Usage

```bash
python agent.py
```

### Query modes

**Streaming (live) mode** — default when `his_time_range` is empty. On each run the agent queries the window:

```
[now - query_time_offset_seconds - streaming_lookback_seconds,
 now - query_time_offset_seconds)
```

Run the agent on a schedule (e.g. via cron) to continuously ingest new data.

**Historical mode** — set `his_time_range` in `config.ini` to replay a fixed time window:

```ini
his_time_range = 2024-01-01 00:00:00,2024-01-31 23:59:59
```

All times are interpreted as UTC.

## Dataset placeholders in prompts

Prompt text may reference datasets using `{{dataset_name}}` placeholders. Before uploading, the agent fetches all datasets from InsightFinder and replaces each placeholder with the corresponding dataset tag:

```
{{my-dataset}}  →  <dataset id="123"> my-dataset </dataset>
```

## Pagination

The agent uses Elasticsearch Point-in-Time (PIT) + `search_after` pagination when available (ES 7.10+, ES 8.x), falling back to `from`/`size` offset pagination on older clusters.
