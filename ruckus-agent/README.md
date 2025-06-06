# Ruckus Agent Configuration Guide

## Overview

The Ruckus Agent uses an INI configuration file to connect to your Ruckus Wireless Controller and send metrics to InsightFinder. This guide explains how to configure the agent properly.

## Configuration File Location

The configuration file should be placed at: `configs/config.ini` (relative to the executable)

## Configuration Sections

### [ruckus] - Ruckus Controller Settings

Configure connection to your Ruckus Wireless Controller:

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `controller_host` | Yes | - | IP address or hostname of Ruckus controller |
| `controller_port` | No | 8443 | HTTPS port for Ruckus controller API |
| `username` | Yes | - | Username for Ruckus controller authentication |
| `password` | Yes | - | Password for Ruckus controller authentication |
| `api_version` | No | v10_0 | Ruckus API version (v10_0, v11_0, v11_1, etc.) |
| `verify_ssl` | No | false | Enable/disable SSL certificate verification |

### [insightfinder] - InsightFinder Settings

Configure connection to InsightFinder platform:

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `server_url` | Yes | - | InsightFinder server URL (e.g., https://app.insightfinder.com) |
| `username` | Yes | - | InsightFinder username |
| `license_key` | Yes | - | InsightFinder license key |
| `project_name` | Yes | - | InsightFinder project name |
| `system_name` | Yes | project_name | System name for grouping |
| `project_type` | No | Metric | Project type (Metric, Log, Trace, etc.) |
| `cloud_type` | No | OnPremise | Cloud type (OnPremise, AWS, Azure, GCP) |
| `instance_type` | No | OnPremise | Instance type |
| `is_container` | No | false | Set to true if running in container |
| `sampling_interval` | No | 300 | Data collection interval in seconds |

### [agent] - Agent Settings

Configure agent behavior:

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `log_level` | No | INFO | Logging level (DEBUG, INFO, WARN, ERROR) |
| `data_format` | No | JSON | Data format (for future use) |
| `timezone` | No | UTC | Timezone for timestamps |
| `filters_include` | No | - | Comma-separated list of AP filters to include |
| `filters_exclude` | No | - | Comma-separated list of AP filters to exclude |

### [state] - State Management

Internal state tracking (automatically managed):

| Parameter | Description |
|-----------|-------------|
| `last_collection_timestamp` | Last successful data collection timestamp |

## Sample Configuration File

Create a file named `config.ini` in the `configs/` directory:

```ini
# Ruckus Agent Configuration File
# Place this file at: configs/config.ini

[agent]
# Agent behavior settings
log_level = INFO
data_format = JSON
timezone = UTC
filters_include = 
filters_exclude = 

[ruckus]
# Ruckus Wireless Controller Configuration
controller_host = 192.168.1.100
controller_port = 8443
username = your_ruckus_username
password = your_ruckus_password
api_version = v11_1
verify_ssl = false

[insightfinder]
# InsightFinder Platform Configuration
server_url = https://app.insightfinder.com
username = your_if_username
license_key = your_license_key_here
project_name = RuckusWiFiMonitoring
system_name = RuckusController
project_type = Metric
cloud_type = OnPremise
instance_type = OnPremise
is_container = false
sampling_interval = 300

[state]
# Internal state (automatically managed)
last_collection_timestamp = 0
```

## Configuration Steps

### Step 1: Create Configuration Directory

```bash
mkdir -p configs
```

### Step 2: Create Configuration File

Copy the sample configuration above to `configs/config.ini` and modify the values:

```bash
cp config.ini.example configs/config.ini
nano configs/config.ini
```

### Step 3: Configure Ruckus Controller

1. **Controller Host**: Enter your Ruckus controller's IP address or hostname
2. **Credentials**: Use an admin or read-only user account
3. **API Version**: Check your controller's firmware version:
   - SmartZone 5.x: use `v10_0`
   - SmartZone 6.x: use `v11_0` or `v11_1`
4. **SSL**: Set `verify_ssl = false` for self-signed certificates

### Step 4: Configure InsightFinder

1. **Server URL**: Server URL
2. **Credentials**: Get from your InsightFinder account settings
3. **Project Name**: Choose a descriptive name (will be created automatically)
4. **Sampling Interval**: Recommended 300 seconds (5 minutes) for WiFi metrics


## Configuration Validation

The agent validates your configuration on startup and will report errors for:

- Missing required fields
- Invalid URLs or hostnames  
- Unreachable controllers or InsightFinder servers
- Invalid credentials
- Network connectivity issues

### Debug Mode

Enable debug logging for detailed troubleshooting:

```ini
[agent]
log_level = DEBUG
```

This will provide detailed API requests, responses, and internal processing information.