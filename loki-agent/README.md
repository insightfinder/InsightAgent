# Loki Agent Configuration Guide

This guide provides comprehensive documentation for configuring the Loki Agent, which collects logs from Grafana Loki and forwards them to InsightFinder for analysis.

## Overview

The Loki Agent uses a YAML configuration file (`configs/config.yaml`) that defines three main sections:
- **Agent Configuration**: General agent settings
- **Loki Configuration**: Connection and query settings for Grafana Loki
- **InsightFinder Configuration**: Connection and project settings for InsightFinder

## Configuration File Structure

```yaml
agent:
  # Agent-specific settings
loki:
  # Loki connection and query configuration
insightfinder:
  # InsightFinder connection and project settings
```

## Agent Configuration

Controls general agent behavior, logging settings, and operation mode.

```yaml
agent:
  data_format: "json"              # Data format for processing (default: "json")
  timezone: "UTC"                  # Timezone for timestamp processing (default: "UTC")
  log_level: "INFO"                # Logging level: DEBUG, INFO, WARN, ERROR (default: "INFO")
  filters_include: ""              # Include filters (optional)
  filters_exclude: ""              # Exclude filters (optional)

  # Operation mode (default: "continuous")
  mode: "continuous"

  # Required for historical and stream_historical modes
  # Accepted formats: RFC3339 "2024-01-01T00:00:00Z" or date-only "2024-01-01"
  start_time: ""
  end_time: ""                     # Leave blank to default to current time

  # historical mode: directory where downloaded NDJSON files are written
  download_path: "./loki_downloads"

  # replay mode: path to a single .ndjson file or a directory of .ndjson files
  replay_path: ""

  # stream_historical / replay: seconds to wait between batches (0 = maximum speed)
  stream_chunk_interval: 0
```

### Agent Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data_format` | String | `"json"` | Format for data processing |
| `timezone` | String | `"UTC"` | Timezone for timestamp processing. Must be a valid timezone (e.g., "America/New_York") |
| `log_level` | String | `"INFO"` | Logging verbosity level |
| `filters_include` | String | `""` | Filters to include specific log entries |
| `filters_exclude` | String | `""` | Filters to exclude specific log entries |
| `mode` | String | `"continuous"` | Operation mode. See [Operation Modes](#operation-modes) |
| `start_time` | String | `""` | Start of the historical time range. Required for `historical` and `stream_historical` modes. Accepts RFC3339 (`"2024-01-01T00:00:00Z"`) or date-only (`"2024-01-01"`) |
| `end_time` | String | `""` | End of the historical time range. Defaults to current time if blank |
| `download_path` | String | `"./loki_downloads"` | Directory where NDJSON files are written in `historical` mode. Required for that mode |
| `replay_path` | String | `""` | File or directory of `.ndjson` files to send to InsightFinder in `replay` mode. Required for that mode |
| `stream_chunk_interval` | Integer | `0` | Seconds to wait between batches in `stream_historical` and `replay` modes. `0` = no wait |

## Operation Modes

The agent supports four operation modes controlled by `agent.mode`.

### `continuous` (default)

Polls Loki every `sampling_interval` seconds and forwards new log entries to InsightFinder indefinitely.

```yaml
agent:
  mode: "continuous"

insightfinder:
  sampling_interval: 60
```

### `historical`

Downloads all logs from `start_time` to `end_time` and writes them to local NDJSON files. Exits when done. **InsightFinder connectivity is not required** for this mode.

The time range is walked in `sampling_interval`-sized chunks. One file is created per enabled query:

```
loki_downloads/
  my_query_1704067200_1704153600.ndjson
```

Each line in the file is a JSON-encoded InsightFinder log entry (with all transformations — tag extraction, component name, sensitive data masking — already applied).

```yaml
agent:
  mode: "historical"
  start_time: "2024-01-01T00:00:00Z"
  end_time: "2024-01-02T00:00:00Z"   # blank = now
  download_path: "./loki_downloads"
```

### `replay`

Reads the NDJSON files produced by `historical` mode and streams each entry to InsightFinder. Acts as a replay client — useful for re-sending previously downloaded logs without querying Loki again.

`replay_path` may be a single `.ndjson` file or a directory (all `*.ndjson` files are replayed in sorted order).

```yaml
agent:
  mode: "replay"
  replay_path: "./loki_downloads"
  stream_chunk_interval: 1    # optional: wait 1s between batches of 1000 entries
```

### `stream_historical`

Walks `start_time` to `end_time` in `sampling_interval`-sized chunks and streams each chunk directly to InsightFinder — no files are written. Use `stream_chunk_interval` to pace the replay.

```yaml
agent:
  mode: "stream_historical"
  start_time: "2024-01-01T00:00:00Z"
  end_time: "2024-01-02T00:00:00Z"
  stream_chunk_interval: 0    # 0 = maximum speed
```

### Mode Comparison

| Mode | Reads from | Writes to | IF required | Exits when done |
|------|-----------|-----------|-------------|-----------------|
| `continuous` | Loki (live) | InsightFinder | Yes | No (runs forever) |
| `historical` | Loki | Local NDJSON files | No | Yes |
| `replay` | Local NDJSON files | InsightFinder | Yes | Yes |
| `stream_historical` | Loki | InsightFinder | Yes | Yes |

## Loki Configuration

Defines connection settings and queries for Grafana Loki.

```yaml
loki:
  base_url: "http://localhost:46339"    # Loki server URL (required)
  username: "admin"                     # Basic auth username (optional)
  password: "admin"                     # Basic auth password (optional)
  verify_ssl: false                     # SSL certificate verification (default: false)
  max_concurrent_requests: 10           # Maximum concurrent requests (default: 10)
  max_retries: 3                        # Maximum retry attempts (default: 3)
  query_timeout: 60                     # Query timeout in seconds (default: 60)
  max_entries_per_query: 1000           # Maximum entries per query (default: 1000)
  
  # Instance name configuration
  default_instance_name_field: "container"    # Default field for instance names (Options: "", "container", "instance", "node_name", "pod", "app")
  
  queries:                              # List of LogQL queries to execute
    - name: "query_name"                # Unique query identifier (required)
      query: "{namespace=\"example\"}"   # LogQL query string (required)
      enabled: true                     # Enable/disable query (default: true)
      max_entries: 1000                 # Override default max entries (optional)
      labels:                           # Additional labels for the query (optional)
        source: "application"
        type: "logs"
      # Field mapping options (all optional)
      instance_name_field: "pod"              # Override default instance field
      component_name_field: "app"             # Field for component name
      container_name_field: "container"       # Field for container name (appended to instance)
```

### Loki Configuration Options

| Parameter | Type | Default | Required | Description |
|-----------|------|---------|----------|-------------|
| `base_url` | String | - | Yes | Loki server base URL |
| `username` | String | `""` | No | Basic authentication username |
| `password` | String | `""` | No | Basic authentication password |
| `verify_ssl` | Boolean | `false` | No | Whether to verify SSL certificates |
| `max_concurrent_requests` | Integer | `10` | No | Maximum number of concurrent requests to Loki |
| `max_retries` | Integer | `3` | No | Maximum number of retry attempts for failed requests |
| `query_timeout` | Integer | `60` | No | Query timeout in seconds |
| `max_entries_per_query` | Integer | `1000` | No | Default maximum entries per query |
| `default_instance_name_field` | String | `""` | No | Default field for instance names. Options: `""` (skip), `"container"`, `"instance"`, `"node_name"`, `"pod"`, `"app"` |

### Query Configuration

Each query in the `queries` array supports the following options:

| Parameter | Type | Default | Required | Description |
|-----------|------|---------|----------|-------------|
| `name` | String | - | Yes | Unique identifier for the query |
| `query` | String | - | Yes | LogQL query string |
| `enabled` | Boolean | `true` | No | Whether the query is active |
| `max_entries` | Integer | Global default | No | Override maximum entries for this query |
| `labels` | Map | `{}` | No | Additional labels to attach to log entries |
| `instance_name_field` | String | `""` | No | Override default instance field. Options: `""`, `"container"`, `"instance"`, `"node_name"`, `"pod"`, `"app"` |
| `component_name_field` | String | `""` | No | Field to extract component name from. Options: `"container"`, `"instance"`, `"node_name"`, `"pod"`, `"app"` |
| `container_name_field` | String | `""` | No | Field to extract container name from (appended to instance). Options: `"container"`, `"instance"`, `"node_name"`, `"pod"`, `"app"` |
| `sensitive_data_filters` | List | `[]` | No | List of regex patterns to mask sensitive data. See [Sensitive Data Filtering](#sensitive-data-filtering) |

### Sensitive Data Filtering

Each query can define a list of regex-replacement pairs under `sensitive_data_filters`. The agent applies every filter to each log message **before** sending to InsightFinder (and before writing to NDJSON in `historical` mode).

```yaml
queries:
  - name: "application_logs"
    query: '{namespace="production"}'
    enabled: true
    sensitive_data_filters:
      - regex: "password=\\S+"
        replacement: "password=***"
      - regex: "\\b\\d{4}[- ]?\\d{4}[- ]?\\d{4}[- ]?\\d{4}\\b"
        replacement: "[CARD_REDACTED]"
      - regex: "Bearer\\s+[A-Za-z0-9\\-._~+/]+=*"
        replacement: "Bearer [TOKEN_REDACTED]"
```

Each entry in the list has two fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `regex` | String | Yes | A valid Go regular expression to match against the log message |
| `replacement` | String | Yes | The string to substitute for every match. Use `""` to delete matches |

**Notes:**
- Filters are applied in the order they are listed.
- Compiled regexes are cached per query; there is no repeated compilation overhead.
- Invalid regex patterns are rejected at startup with a configuration validation error.

### Example Queries

```yaml
loki:
  # Use pod names as default instance names
  default_instance_name_field: "pod"
  
  queries:
    # Application audit logs with component tracking
    - name: "insightfinder_audit_logs"
      query: '{namespace="insightfinder",pod=~".*appserver.*"} |= `com.insightfinder.models.AuditLog`'
      enabled: true
      labels:
        source: "insightfinder"
        type: "audit"
      component_name: "app"           # Use app field for component classification
      container_name: "container"     # Append container name to instance
      # Result: instance="java-container_appserver-pod-123", component="insightfinder-app"
    
    # Error logs with node-level tracking
    - name: "application_errors"
      query: '{namespace="insightfinder"} |~ "ERROR|Exception|FATAL"'
      enabled: true
      labels:
        source: "insightfinder"
        type: "error"
      instance_name: "node_name"      # Override: use node names for error tracking
      component_name: "pod"           # Use pod for error categorization
      # Result: instance="worker-node-1", component="error-handler-pod-abc"
    
    # Kubernetes events without instance tracking
    - name: "kubernetes_events"
      query: '{namespace=~"kube-.*|default"} |= "Event"'
      enabled: false
      labels:
        source: "kubernetes"
        type: "event"
      instance_name: ""               # Skip instance names for cluster events
      component_name: "namespace"     # Would use namespace if it were a valid field
      # Result: no instance tag, logs grouped by query only
```

## Instance Name Configuration

The loki-agent provides flexible configuration for instance naming. You can control how instance names, component names, and container names are extracted and used when sending logs to InsightFinder.

### Configuration Fields

1. **default_instance_name_field** (Loki level): Global default field to extract instance names from when query-specific instance names are not configured
2. **instance_name_field** (Query level): Field to extract instance name for this specific query
3. **component_name_field** (Query level): Field to extract component name for this specific query  
4. **container_name_field** (Query level): Field to extract container name for this specific query

### Valid Field Names

All field name parameters accept the following values:
- `""` (empty): Skip this field extraction
- `container`: Extract from container field
- `instance`: Extract from instance field
- `node_name`: Extract from node_name field
- `pod`: Extract from pod field
- `app`: Extract from app field

### Tag Generation Behavior

When field values are successfully extracted, they are used to generate tags in the format: `container_instance`

**Important**: 
- If both `default_instance_name_field` and query-specific `instance_name_field` are empty/unset, **no container_instance tag will be generated**
- If a field is configured but the actual log entry doesn't contain that field, the extraction is skipped
- Component and container name extractions work independently and will create their respective tags when values are found

## InsightFinder Configuration

Defines connection settings and project configuration for InsightFinder.

```yaml
insightfinder:
  server_url: "https://app.insightfinder.com"    # InsightFinder server URL (default: "https://app.insightfinder.com")
  username: "your_username"                      # InsightFinder username (required)
  license_key: "your_license_key"                # InsightFinder license key (required)
  
  # Project Configuration
  logs_project_name: "loki-logs"                 # Project name for logs (required)
  logs_system_name: "loki-system"                # System name for logs (optional)
  logs_project_type: "LOG"                       # Project type (default: "LOG")
  
  # Collection Settings
  sampling_interval: 60                          # Collection interval in seconds (default: 60)
  cloud_type: "OnPremise"                        # Cloud type (default: "OnPremise")
  instance_type: "OnPremise"                     # Instance type (default: "OnPremise")
  is_container: true                             # Whether running in container (default: false)
  
  # Proxy Settings (optional)
  http_proxy: ""                                 # HTTP proxy URL
  https_proxy: ""                                # HTTPS proxy URL
  
  # Advanced Settings
  chunk_size: 2097152                            # Chunk size in bytes (default: 2MB)
  max_packet_size: 10485760                      # Maximum packet size in bytes (default: 10MB)
  retry_times: 3                                 # Number of retry attempts (default: 3)
  retry_interval: 5                              # Retry interval in seconds (default: 5)
```

### InsightFinder Configuration Options

| Parameter | Type | Default | Required | Description |
|-----------|------|---------|----------|-------------|
| `server_url` | String | `"https://app.insightfinder.com"` | No | InsightFinder server URL |
| `username` | String | - | Yes | InsightFinder account username |
| `license_key` | String | - | Yes | InsightFinder license key |
| `logs_project_name` | String | - | Yes | Project name for log data |
| `logs_system_name` | String | `""` | No | System name identifier |
| `logs_project_type` | String | `"LOG"` | No | Project type (should be "LOG" for this agent) |
| `sampling_interval` | Integer | `60` | No | Collection interval in seconds |
| `cloud_type` | String | `"OnPremise"` | No | Cloud provider type |
| `instance_type` | String | `"OnPremise"` | No | Instance type identifier |
| `is_container` | Boolean | `false` | No | Whether agent runs in a container |
| `http_proxy` | String | `""` | No | HTTP proxy server URL |
| `https_proxy` | String | `""` | No | HTTPS proxy server URL |
| `chunk_size` | Integer | `2097152` | No | Data chunk size in bytes (2MB) |
| `max_packet_size` | Integer | `10485760` | No | Maximum packet size in bytes (10MB) |
| `retry_times` | Integer | `3` | No | Number of retry attempts for failed requests |
| `retry_interval` | Integer | `5` | No | Retry interval in seconds |

## Environment-Specific Configurations

### Development Environment

```yaml
agent:
  log_level: "DEBUG"

loki:
  base_url: "http://localhost:3100"
  verify_ssl: false
  max_concurrent_requests: 5

insightfinder:
  server_url: "https://stg.insightfinder.com"
  sampling_interval: 30
```

### Production Environment

```yaml
agent:
  log_level: "INFO"

loki:
  base_url: "https://loki.example.com"
  verify_ssl: true
  max_concurrent_requests: 20
  max_retries: 5

insightfinder:
  server_url: "https://app.insightfinder.com"
  sampling_interval: 60
  chunk_size: 4194304  # 4MB for high volume
```

## Configuration Validation

The agent validates the configuration on startup and will fail if required fields are missing or invalid:

### Required Fields
- `loki.base_url`
- `insightfinder.username`
- `insightfinder.license_key`
- `insightfinder.logs_project_name`
- At least one enabled query in `loki.queries`

### Validation Rules
- Each query must have a unique `name`
- Each query must have a non-empty `query` string
- `timezone` must be a valid timezone identifier
- `sampling_interval` must be greater than 0
- `mode` must be one of: `continuous`, `historical`, `stream_historical`, `replay`
- `start_time` is required when `mode` is `historical` or `stream_historical`
- `download_path` is required when `mode` is `historical`
- `replay_path` is required when `mode` is `replay`
- All `sensitive_data_filters[].regex` values must be valid Go regular expressions

## Usage Examples

### Basic Configuration

```yaml
agent:
  log_level: "INFO"

loki:
  base_url: "http://localhost:3100"
  queries:
    - name: "all_logs"
      query: '{job="app"}'
      enabled: true

insightfinder:
  username: "myuser"
  license_key: "mylicensekey"
  logs_project_name: "my-project"
```

### Advanced Configuration with Multiple Queries

```yaml
agent:
  log_level: "DEBUG"
  timezone: "America/New_York"

loki:
  base_url: "https://loki.company.com"
  username: "loki-user"
  password: "loki-pass"
  verify_ssl: true
  max_concurrent_requests: 15
  query_timeout: 120
  
  queries:
    - name: "application_logs"
      query: '{namespace="production", app="myapp"}'
      enabled: true
      max_entries: 2000
      labels:
        environment: "production"
        source: "application"
    
    - name: "error_logs"
      query: '{namespace="production"} |~ "ERROR|FATAL"'
      enabled: true
      labels:
        severity: "error"
        
    - name: "audit_logs"
      query: '{namespace="production", component="audit"}'
      enabled: false

insightfinder:
  server_url: "https://app.insightfinder.com"
  username: "company-user"
  license_key: "abc123def456ghi789"
  logs_project_name: "production-logs"
  logs_system_name: "kubernetes-cluster"
  sampling_interval: 300  # 5 minutes
  cloud_type: "AWS"
  instance_type: "EC2"
  is_container: true
  chunk_size: 4194304     # 4MB
  retry_times: 5
```

## Configuration Loading

The agent loads configuration from `configs/config.yaml` by default. You can specify a different path by modifying the `main.go` file or by implementing command-line argument parsing.

## Troubleshooting

### Common Configuration Issues

1. **Missing Required Fields**: Ensure all required fields are provided
2. **Invalid Timezone**: Use valid timezone identifiers (e.g., "UTC", "America/New_York")
3. **Loki Connection Issues**: Verify `base_url`, credentials, and network connectivity
4. **Query Syntax Errors**: Validate LogQL queries using Loki's query interface
5. **SSL Certificate Issues**: Set `verify_ssl: false` for self-signed certificates

### Debug Mode

Enable debug logging to troubleshoot configuration issues:

```yaml
agent:
  log_level: "DEBUG"
```

This will provide detailed logging about configuration loading, validation, and runtime behavior.

## Security Considerations

- Store sensitive information (passwords, license keys) securely
- Use environment variables or secret management systems for production deployments
- Enable SSL verification (`verify_ssl: true`) when using HTTPS endpoints
- Limit `max_concurrent_requests` to avoid overwhelming Loki instances
- Configure appropriate proxy settings for corporate environments

## Performance Tuning

- Adjust `sampling_interval` based on log volume and requirements
- Increase `chunk_size` and `max_packet_size` for high-volume environments
- Use `max_entries_per_query` to limit resource usage
- Configure `max_concurrent_requests` based on system capabilities
- Set appropriate `query_timeout` values for large queries
