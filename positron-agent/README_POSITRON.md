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

## Device Inventory Enrichment

If `device_inventory.api_key` and `device_inventory.base_url` are set in `configs/config.yaml`, the agent looks up each endpoint and device in the internal Device Inventory (Asset Registry) API - by MAC (endpoints only), then serial number, then own name (first match wins) - and caches the result in `devicelookup.json` (refreshed every `device_inventory.refresh_hours`, default 24; a device seen for the first time is always looked up immediately, regardless of that timer). If the two settings are left blank, enrichment is skipped entirely and no device is ever matched.

Values sent to InsightFinder, in priority order:

- **Instance name** (`in`): Inventory MAC (`MAC {mac}`, endpoints only) > Inventory serial (`SERIAL {serial}`) > Inventory object key (`JIRAKEY {object_key}`) > the device's own name (cleaned - `_`/`:` become `-`). If none of these are available, the device is **dropped** (not sent to InsightFinder) rather than sent under any other identifier. Values are never upper/lower-cased.
- **Instance display name** (`idn`): the device's own name as reported, raw/uncleaned - never falls back to the Inventory's name field. For devices this is always `name`; for endpoints, Positron exposes two competing name fields (`confEndpointName` and `confUserName`) that aren't reliably kept in sync with each other, so `confEndpointName` is used whenever it looks like a real name, falling back to `confUserName` only when `confEndpointName` is empty or has degraded to a bare port/slot number (e.g. `"10105"`).
- **Component name** (`cn`): Inventory's `component_name` only (`{manufacturer}-{device_class}`, only set when both are present). Omitted if not in Inventory - no default.
- **Zone** (`z`): Inventory's `venue` only. Omitted if not in Inventory - no default.
- **IP address** (`i`): Inventory's `ip_address` > the device's own reported IP (devices only - endpoints report none; excludes the `0.0.0.0` placeholder). Omitted if both are empty.

`idn`/`cn`/`i`/`z` are packed into a single JSON string in the `im` field of each instance (not sent as flat top-level keys) - this is required for InsightFinder to pick up the display name correctly.

`devicelookup.json` is a runtime cache regenerated on every run (gitignored) - delete it to force a full re-lookup.

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
- `DS PHY rate`, `US PHY rate` - Downstream/upstream physical layer rate (`rxPhyRate`/`txPhyRate`)
- `DS Max BW`, `US Max BW` - Downstream/upstream max throughput (`rxMaxXput`/`txMaxXput`)

### Device Metrics
- `Ports`, `Endpoints`, `Subscribers`, `Bandwidths` - Capacity counts reported by `/device/list`

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
