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

Controls general agent behavior and logging settings.

```yaml
agent:
  data_format: "json"              # Data format for processing (default: "json")
  timezone: "UTC"                  # Timezone for timestamp processing (default: "UTC")
  log_level: "INFO"                # Logging level: DEBUG, INFO, WARN, ERROR (default: "INFO")
  filters_include: ""              # Include filters (optional)
  filters_exclude: ""              # Exclude filters (optional)
```

### Agent Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data_format` | String | `"json"` | Format for data processing |
| `timezone` | String | `"UTC"` | Timezone for timestamp processing. Must be a valid timezone (e.g., "America/New_York") |
| `log_level` | String | `"INFO"` | Logging verbosity level |
| `filters_include` | String | `""` | Filters to include specific log entries |
| `filters_exclude` | String | `""` | Filters to exclude specific log entries |

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
  default_instance_name: "container"    # Default field for instance names (Options: "", "container", "instance", "node_name", "pod", "app")
  
  queries:                              # List of LogQL queries to execute
    - name: "query_name"                # Unique query identifier (required)
      query: "{namespace=\"example\"}"   # LogQL query string (required)
      enabled: true                     # Enable/disable query (default: true)
      max_entries: 1000                 # Override default max entries (optional)
      labels:                           # Additional labels for the query (optional)
        source: "application"
        type: "logs"
      # Field mapping options (all optional)
      instance_name: "pod"              # Override default instance field
      component_name: "app"             # Field for component name
      container_name: "container"       # Field for container name (appended to instance)
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
| `default_instance_name` | String | `""` | No | Default field for instance names. Options: `""` (skip), `"container"`, `"instance"`, `"node_name"`, `"pod"`, `"app"` |

### Query Configuration

Each query in the `queries` array supports the following options:

| Parameter | Type | Default | Required | Description |
|-----------|------|---------|----------|-------------|
| `name` | String | - | Yes | Unique identifier for the query |
| `query` | String | - | Yes | LogQL query string |
| `enabled` | Boolean | `true` | No | Whether the query is active |
| `max_entries` | Integer | Global default | No | Override maximum entries for this query |
| `labels` | Map | `{}` | No | Additional labels to attach to log entries |
| `instance_name` | String | `""` | No | Override default instance field. Options: `""`, `"container"`, `"instance"`, `"node_name"`, `"pod"`, `"app"` |
| `component_name` | String | `""` | No | Field to extract component name from. Options: `"container"`, `"instance"`, `"node_name"`, `"pod"`, `"app"` |
| `container_name` | String | `""` | No | Field to extract container name from (appended to instance). Options: `"container"`, `"instance"`, `"node_name"`, `"pod"`, `"app"` |

### Example Queries

```yaml
loki:
  # Use pod names as default instance names
  default_instance_name: "pod"
  
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

The Loki Agent provides flexible configuration for extracting instance names, component names, and container names from log entries. This system allows you to control how logs are tagged and organized in InsightFinder.

### Overview

The agent extracts metadata from log entries using field mappings. You can specify which fields from the log stream should be used for:
- **Instance Name (Tag)**: Primary identifier for the log source
- **Component Name**: Secondary categorization (optional)
- **Container Name**: Additional identifier that gets appended to instance name

### Available Fields

The following fields are available for extraction from log entries:

| Field Name | Description | Example Value |
|------------|-------------|---------------|
| `container` | Container name from the log stream | `"nginx-container"` |
| `instance` | Instance identifier from the log stream | `"web-instance-1"` |
| `node_name` | Kubernetes node name | `"worker-node-1"` |
| `pod` | Kubernetes pod name | `"web-pod-abc123"` |
| `app` | Application label from the log stream | `"web-app"` |

### Configuration Structure

```yaml
loki:
  # Global default field for instance names
  default_instance_name: "container"    # Options: "", "container", "instance", "node_name", "pod", "app"
  
  queries:
    - name: "example_query"
      query: '{namespace="production"}'
      
      # Query-specific field mappings (all optional)
      instance_name: "pod"              # Override default instance field
      component_name: "app"             # Field to use for component name
      container_name: "container"       # Field to use for container name
```

### Default Instance Name

The `default_instance_name` field in the Loki configuration sets the global default for all queries:

```yaml
loki:
  default_instance_name: "pod"    # Use pod names as default instance names
```

**Special Behavior:**
- **Empty value (`""`)**: Skip instance name creation entirely - logs will have no instance tags
- **Valid field name**: Use that field as the default for all queries
- **Query override**: Individual queries can override the default using `instance_name`

### Query-Specific Configuration

Each query can customize field extraction independently:

#### Instance Name Override
```yaml
queries:
  - name: "kubernetes_pods"
    query: '{namespace="kube-system"}'
    instance_name: "pod"              # Use pod field instead of default
```

#### Component Name Extraction
```yaml
queries:
  - name: "application_logs"
    query: '{app="web-service"}'
    component_name: "app"             # Extract component from app field
```

#### Container Name Appending
```yaml
queries:
  - name: "multi_container_pods"
    query: '{namespace="production"}'
    instance_name: "pod"              # Use pod for instance
    container_name: "container"       # Append container name
    # Result: "nginx-container_web-pod-123"
```

### Tag Generation Logic

The final instance tag (used in InsightFinder) is generated using this logic:

1. **Determine instance field**:
   - Use query's `instance_name` if specified
   - Otherwise use global `default_instance_name`
   - If both are empty, skip tag creation

2. **Extract instance value**:
   - Get value from the determined field in the log entry
   - If field is empty or doesn't exist, use empty string

3. **Append container name** (if specified):
   - Extract value from `container_name` field
   - Prepend to instance name with underscore: `{container}_{instance}`

4. **Clean and finalize**:
   - Apply naming rules and sanitization
   - If final result is empty, no tag is created

### Configuration Examples

#### Example 1: Skip Instance Names
```yaml
loki:
  default_instance_name: ""           # Skip instance names globally
  queries:
    - name: "logs_without_instances"
      query: '{namespace="logging"}'
      # No instance names will be created
```

#### Example 2: Use Pod Names by Default
```yaml
loki:
  default_instance_name: "pod"        # Use pod names as default
  queries:
    - name: "kubernetes_logs"
      query: '{namespace="production"}'
      # Will use pod names from log entries
```

#### Example 3: Mixed Configuration
```yaml
loki:
  default_instance_name: "container"  # Default to container names
  queries:
    - name: "pod_based_logs"
      query: '{component="frontend"}'
      instance_name: "pod"            # Override: use pod names
      component_name: "app"           # Add component from app field
      
    - name: "node_logs"
      query: '{job="node-exporter"}'
      instance_name: "node_name"      # Override: use node names
      
    - name: "detailed_logs"
      query: '{namespace="services"}'
      instance_name: "pod"            # Use pod names
      container_name: "container"     # Append container names
      component_name: "app"           # Add component classification
      # Result: instance="nginx_web-pod-123", component="web-service"
```

#### Example 4: Application-Specific Tagging
```yaml
loki:
  default_instance_name: "app"        # Use application names
  queries:
    - name: "microservice_logs"
      query: '{namespace="microservices"}'
      component_name: "pod"           # Use pod for component grouping
      container_name: "container"     # Track specific containers
      # Result: instance="api-container_user-service", component="user-service-pod-abc"
      
    - name: "database_logs"
      query: '{app="database"}'
      instance_name: "instance"       # Use instance field for databases
      # Result: instance="db-primary-1"
```

### Field Mapping Reference

| Log Stream Field | Typical Content | Use Case |
|------------------|----------------|----------|
| `namespace` | `"production"`, `"kube-system"` | Not configurable for tagging |
| `container` | `"nginx"`, `"app-server"` | Good for container-focused environments |
| `instance` | `"web-01"`, `"db-primary"` | Good for traditional instance-based deployments |
| `node_name` | `"worker-node-1"` | Good for node-level monitoring |
| `pod` | `"web-deployment-abc123"` | Good for Kubernetes pod tracking |
| `app` | `"web-service"`, `"user-api"` | Good for application-level grouping |

### Best Practices

1. **Choose Consistent Fields**: Use the same field mapping strategy across related queries
2. **Consider Cardinality**: Avoid fields that create too many unique instance names
3. **Test Empty Values**: Ensure your configuration handles missing fields gracefully
4. **Use Component Names**: Leverage component names for additional categorization
5. **Document Your Strategy**: Keep track of which fields you're using for what purpose

### Troubleshooting

**No instance names appearing:**
- Check that `default_instance_name` is not empty
- Verify the specified field exists in your log entries
- Ensure queries don't override with empty `instance_name`

**Unexpected instance names:**
- Check field values in actual log entries
- Verify field name spelling (e.g., `node_name` not `node`)
- Test with debug logging enabled

**Too many unique instances:**
- Consider using higher-level fields (e.g., `app` instead of `pod`)
- Use component names for detailed categorization instead of instance names

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
