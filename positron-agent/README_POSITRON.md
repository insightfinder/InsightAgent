# Positron Agent

A data collection agent that monitors Positron networks and sends metrics and logs to InsightFinder for analysis and monitoring.

## Overview

The Positron Agent connects to Positron controllers via REST API to collect:

- **Metrics Data**: Endpoint and device performance metrics
- **Log Data**: Alarm and event information

All data is automatically sent to InsightFinder for monitoring, alerting, and analysis.

## Configuration

Edit `configs/config.yaml` to configure the agent:

### Positron Controller Settings
```yaml
positron:
  controller_host: localhost    # Positron controller hostname/IP
  controller_port: 8443        # API port (usually 8443)
  username: xyz               # Basic auth username
  password: 1245              # Basic auth password
  verify_ssl: false           # SSL certificate verification
  max_concurrent_requests: 20  # Max concurrent API requests
```

### InsightFinder Settings
```yaml
insightfinder:
  server_url: https://stg.insightfinder.com
  username: your_username
  license_key: your_license_key
  
  # Metrics Project Configuration
  metrics_project_name: Positron-Metrics
  metrics_system_name: Positron System
  metrics_project_type: Metric
  
  # Logs Project Configuration  
  logs_project_name: Positron-Logs
  logs_system_name: Positron System
  logs_project_type: Log
  
  # Common Configuration
  cloud_type: OnPremise
  instance_type: OnPremise
  sampling_interval: 60        # Data collection interval in seconds
```

## API Endpoints Monitored

### Endpoints API (`/api/v1/endpoint/list/all`)
Collects endpoint performance metrics including:
- Connection state and status
- Throughput (Rx/Tx rates, max throughput)
- Physical layer metrics (wire length, mode)
- Device information (model, firmware, uptime)

### Devices API (`/api/v1/device/list`)
Collects device information including:
- Device capacity (ports, endpoints, subscribers)
- Software versions and hardware details
- Uptime and status information
- NTP configuration

### Alarms API (`/api/v1/alarm/list`)
Collects alarm and event data including:
- System alarms and their severity
- Service-affecting conditions
- Alarm timestamps and status
- Device serial numbers and details

## Metrics Collected

### Endpoint Metrics
- `State`, `Alive`, `FW_Mismatch` - Connection status
- `Xput_Indicator_Mbps`, `Rx_Phy_Rate_Mbps`, `Tx_Phy_Rate_Mbps` - Throughput
- `Rx_Max_Xput_Mbps`, `Tx_Max_Xput_Mbps` - Maximum throughput
- `Rx_Usage_Percent`, `Tx_Usage_Percent` - Usage percentages
- `Wire_Length_Meters`, `Wire_Length_Feet` - Physical layer
- `Mode` - Operating mode (e.g., "coax")
- `Uptime_Seconds` - Device uptime

### Device Metrics
- `Ports_Total`, `Endpoints_Total`, `Subscribers_Total` - Capacity
- `Software_Version`, `Product_Class` - Device info
- `Uptime_Seconds` - Device uptime
- `Firmware_Upgrade_In_Progress` - Status flags

## Usage

### Production Mode
```bash
./positron-agent
```

### Test Mode (Development)
Uncomment the test mode line in `main.go`:
```go
w.EnableTestMode()
```

## Building

```bash
go build -o positron-agent main.go
```

## Project Structure

- `main.go` - Application entry point
- `configs/` - Configuration management
- `positron/` - Positron API client and data structures
- `insightfinder/` - InsightFinder API client
- `worker/` - Data collection orchestration
- `pkg/models/` - Data models and utilities

## Authentication

The agent uses HTTP Basic Authentication to connect to the Positron controller. Ensure the configured username and password have sufficient privileges to access the monitoring APIs.

## Data Flow

1. Agent periodically connects to Positron controller
2. Retrieves data from three API endpoints
3. Converts data to InsightFinder format
4. Sends metrics to InsightFinder metrics project
5. Sends logs to InsightFinder logs project
6. Repeats based on sampling_interval

## Troubleshooting

- Check controller connectivity and credentials
- Verify InsightFinder project configuration
- Review log output for API errors
- Test individual API endpoints manually if needed
