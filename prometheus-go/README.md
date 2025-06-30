# Prometheus InsightAgent

A Go-based monitoring agent that collects metrics from Prometheus and sends them to InsightFinder for analysis and monitoring.

## Overview

This application is a high-performance data collector that:
- Queries metrics from Prometheus endpoints
- Processes and transforms metric data
- Sends processed data to InsightFinder platform
- Supports multiple concurrent configurations
- Provides flexible metric filtering and batching

## Features

- **Multi-configuration Support**: Process multiple Prometheus endpoints simultaneously
- **Flexible Querying**: Support for custom Prometheus queries via configuration files
- **Batch Processing**: Configurable metric batch sizes for optimal performance
- **Authentication Support**: Basic auth, client certificates, and CA bundle verification
- **Instance Filtering**: Regex-based instance whitelisting
- **Historical Data**: Support for querying historical time ranges
- **Debug Mode**: Comprehensive logging for troubleshooting

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Prometheus    │◄───│ InsightAgent-Go  │───►│  InsightFinder  │
│   Endpoints     │    │                  │    │   Platform      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Installation

### Prerequisites

- Go 1.19 or higher
- Access to Prometheus endpoint(s)
- InsightFinder account with valid license key

### Build from Source

```bash
git clone <repository-url>
cd prometheus-go
go mod tidy
go build -o insightagent main.go
```

## Configuration

### Directory Structure

```
prometheus-go/
├── main.go
├── conf.d/
│   ├── config.ini.template
│   └── query.json
└── README.md
```

### Configuration Files

The agent uses configuration files located in the `conf.d/` directory:

1. **Main Configuration** (`*.ini` files): Contains Prometheus connection details and InsightFinder settings
2. **Query Configuration** (`query.json`): Defines Prometheus queries and metric collection rules

### Main Configuration (config.ini)

Copy `conf.d/config.ini.template` to `conf.d/config.ini` and configure:

```ini
[prometheus]
prometheus_uri = http://your-prometheus:9090
user = your_username
password = your_password
verify_certs = true
prometheus_query_json = query.json
instance_field = instance

[insightfinder]
user_name = your_if_username
license_key = your_license_key  
project_name = your_project_name
system_name = your_system_name
project_type = metric
containerize = yes
sampling_interval = 60s
run_interval = 60s
if_url = https://app.insightfinder.com
```

### Query Configuration (query.json)

Define your Prometheus queries:

```json
[
  {
    "query": "{__name__=~'node_.*',job='kubernetes-service-endpoints'}",
    "instance_fields": ["instance"]
  },
  {
    "query": "up",
    "instance_fields": ["instance", "job"]
  }
]
```

## Usage

### Basic Usage

```bash
# Run with default settings
./insightagent

# Run with debug logging
./insightagent -debug

# Specify collector type
./insightagent -collector prometheus
```

### Command Line Options

- `-debug`: Enable debug logging
- `-collector <type>`: Specify collector type (default: prometheus)

### Multiple Configurations

Place multiple `.ini` files in the `conf.d/` directory to run multiple collectors simultaneously:

```
conf.d/
├── prod-cluster.ini
├── staging-cluster.ini
└── dev-cluster.ini
```

Each configuration file will spawn a separate worker thread.

## Configuration Reference

### Prometheus Section

| Parameter | Description | Required |
|-----------|-------------|----------|
| `prometheus_uri` | Prometheus server URL | Yes |
| `user` | Basic auth username | No |
| `password` | Basic auth password | No |
| `verify_certs` | Enable SSL verification | No |
| `ca_certs` | Path to CA bundle | No |
| `client_cert` | Path to client certificate | No |
| `client_key` | Path to client key | No |
| `prometheus_query` | Direct Prometheus query | No |
| `prometheus_query_json` | JSON file with queries | No |
| `prometheus_query_metric_batch_size` | Batch size for queries | No |
| `instance_field` | Field name for instance identification | No |
| `his_time_range` | Historical data time range | No |

### InsightFinder Section

| Parameter | Description | Required |
|-----------|-------------|----------|
| `user_name` | InsightFinder username | Yes |
| `license_key` | InsightFinder license key | Yes |
| `project_name` | Target project name | Yes |
| `system_name` | System name | Yes |
| `project_type` | Project type (metric/log/alert) | Yes |
| `containerize` | Container environment flag | No |
| `sampling_interval` | Data collection interval | No |
| `if_url` | InsightFinder API URL | No |

## Monitoring and Logging

The application provides structured logging with different levels:

- **INFO**: General operational information
- **DEBUG**: Detailed debugging information (use `-debug` flag)
- **ERROR**: Error conditions and failures

Example log output:
```
2024-01-15T10:30:00Z INF Starting InsightAgent...
2024-01-15T10:30:00Z INF Loaded 2 configuration files from conf.d/
2024-01-15T10:30:01Z INF Worker(config) starting...
2024-01-15T10:30:01Z INF Worker(config) finished...
```

## Troubleshooting

### Common Issues

1. **Connection Refused**
   - Verify Prometheus URI is correct
   - Check network connectivity
   - Ensure Prometheus is running

2. **Authentication Failed**
   - Validate username/password
   - Check certificate paths
   - Verify CA bundle

3. **No Data Collected**
   - Review Prometheus queries in query.json
   - Check instance filtering rules
   - Verify metric names exist

4. **InsightFinder Upload Failed**
   - Validate license key
   - Check project name exists
   - Verify InsightFinder URL

### Debug Mode

Enable debug mode for detailed logging:

```bash
./insightagent -debug
```

This will show:
- Detailed HTTP requests/responses
- Query execution details
- Data processing steps
- Error stack traces

## Performance Tuning

### Batch Size Configuration

For large metric sets, configure batch processing:

```ini
prometheus_query_metric_batch_size = 100
batch_metric_filter_regex = node_.*
```

### Sampling Intervals

Adjust collection frequency based on your needs:

```ini
sampling_interval = 30s  # More frequent collection
run_interval = 300s      # Less frequent runs
```

## Support

For issues and questions:
1. Check the troubleshooting section
2. Enable debug mode for detailed logs
3. Review configuration file syntax
4. Contact InsightFinder support

## License

[Add your license information here]