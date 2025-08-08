# Cambium Metrics Collector

A Go application that collects metrics from Cambium Network devices and sends them to InsightFinder for monitoring and analysis.

## Features

- **YAML Configuration**: Easy-to-use YAML configuration file
- **Automated Login**: Uses Playwright to automatically log into Cambium Cloud
- **Concurrent Processing**: Configurable worker pool for efficient device processing
- **InsightFinder Integration**: Direct integration with InsightFinder platform
- **Retry Logic**: Robust error handling with configurable retry attempts
- **Comprehensive Metrics**: Collects device status, radio metrics, and performance data

## Configuration

Create a `config.yaml` file with your settings:

```yaml
agent:
  # Agent behavior settings
  log_level: INFO
  data_format: JSON
  timezone: UTC
  filters_include: ""
  filters_exclude: ""

cambium:
  # Cambium Network Configuration
  email: your-email@domain.com
  password: your-password
  base_url: https://your-cambium-cloud-url/path/to/api
  login_url: https://cloud.cambiumnetworks.com/#/
  max_retries: 3
  worker_count: 10
  collection_interval_seconds: 60

insightfinder:
  # InsightFinder Platform Configuration
  server_url: https://app.insightfinder.com
  username: your-insightfinder-username
  license_key: your-license-key
  project_name: Cambium-AP-Metrics
  system_name: Your System Name
  project_type: Metric
  cloud_type: OnPremise
  instance_type: OnPremise
  is_container: false
  sampling_interval: 60
```

## Installation

1. Install Go (version 1.22 or higher)
2. Install dependencies:
   ```bash
   go mod download
   ```
3. Install Playwright browsers:
   ```bash
   go run github.com/playwright-community/playwright-go/cmd/playwright install
   ```

## Usage

### Basic Usage
```bash
./cambium-metrics-collector
```

### Custom Configuration File
```bash
./cambium-metrics-collector -config /path/to/your/config.yaml
```

## Configuration Options

### Agent Settings
- `log_level`: Logging level (DEBUG, INFO, WARN, ERROR)
- `data_format`: Output data format (JSON)
- `timezone`: Timezone for timestamps (UTC)
- `filters_include`: Include filters (not implemented yet)
- `filters_exclude`: Exclude filters (not implemented yet)

### Cambium Settings
- `email`: Your Cambium Cloud email
- `password`: Your Cambium Cloud password
- `base_url`: Base URL for your Cambium Cloud instance
- `login_url`: Cambium Cloud login URL
- `max_retries`: Maximum retry attempts for failed API calls
- `worker_count`: Number of concurrent workers for device processing
- `collection_interval_seconds`: How often to collect metrics (in seconds)

### InsightFinder Settings
- `server_url`: InsightFinder server URL
- `username`: InsightFinder username
- `license_key`: InsightFinder license key
- `project_name`: Name of the project in InsightFinder
- `system_name`: System name for the project
- `project_type`: Type of project (Metric, Log, etc.)
- `cloud_type`: Cloud deployment type
- `instance_type`: Instance type
- `is_container`: Whether running in a container
- `sampling_interval`: Data sampling interval in seconds

## Collected Metrics

The collector gathers the following metrics from Cambium devices:

### Core Device Metrics
- **Status**: Device online/offline status (1/0)
- **Available Memory**: Memory usage percentage
- **CPU Utilization**: CPU usage percentage

### Radio Metrics (by Band: 2.4GHz, 5GHz, 6GHz)
- **Num Clients**: Number of connected clients
- **UL Throughput**: Uplink throughput (Mbps)
- **DL Throughput**: Downlink throughput (Mbps)
- **Noise Floor**: Radio noise floor (dBm)
- **Channel Utilization**: Channel utilization percentage

## Output

- Metrics are sent directly to InsightFinder via API
- Comprehensive logging shows collection progress and any errors

## Troubleshooting

### Common Issues

1. **Login Failed**: Check your email/password in the configuration
2. **API Errors**: Verify your Cambium Cloud URL and network connectivity
3. **InsightFinder Errors**: Check your license key and project settings
4. **Permission Errors**: Ensure the application has write permissions for log files

### Debug Mode
Set `log_level: DEBUG` in your configuration for detailed logging.

### Playwright Issues
If you encounter browser-related errors:
```bash
go run github.com/playwright-community/playwright-go/cmd/playwright install --with-deps
```

## Dependencies

- [Playwright Go](https://github.com/playwright-community/playwright-go)
- [Logrus](https://github.com/sirupsen/logrus)
- [YAML v3](https://gopkg.in/yaml.v3)
- [Requests](https://github.com/carlmjohnson/requests)
- [Go QueryString](https://github.com/google/go-querystring)

## License

This project is licensed under the MIT License - see the LICENSE file for details.
