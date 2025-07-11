# Stream Control Configuration Guide

This document explains how to configure the Zabbix Webhook Agent to control which types of alerts are sent to InsightFinder.

## Overview

The `stream_resolved_alerts` setting allows you to control whether RESOLVED alerts are sent to the InsightFinder API endpoint (`/api/v1/customprojectrawdata`). This is useful in scenarios where you only want to track PROBLEM alerts in InsightFinder but still want incident investigation to work properly for resolved events.

## Key Behavior

- **When `stream_resolved_alerts = true` (default)**:
  - Both PROBLEM and RESOLVED alerts are sent to `/api/v1/customprojectrawdata`
  - Incident investigation API is called for RESOLVED events
  
- **When `stream_resolved_alerts = false`**:
  - Only PROBLEM alerts are sent to `/api/v1/customprojectrawdata`
  - RESOLVED alerts are NOT sent to `/api/v1/customprojectrawdata`
  - Incident investigation API is STILL called for RESOLVED events

## Configuration Methods

### 1. Multi-Project Configuration Files

For configurations stored in `config/insightfinder/*.ini` files:

```ini
[insightfinder]
base_url = https://app.insightfinder.com
username = your_username
password = your_password
license_key = your_license_key
project_name = your_project_name
system_name = your_system_name

[project_settings]
instance_type = Zabbix
project_cloud_type = Zabbix
data_type = Log
insight_agent_type = Custom
sampling_interval = 60
sampling_interval_in_seconds = 60
# Control resolved alert streaming
stream_resolved_alerts = false  # Set to false to disable resolved alerts
```

### 2. Legacy Environment Variables

For `.env` file configuration:

```bash
API_KEY=your_secret_api_key_here
LOG_LEVEL=INFO
INSIGHTFINDER_BASE_URL=https://app.insightfinder.com
INSIGHTFINDER_USERNAME=your_username
INSIGHTFINDER_LICENSE_KEY=your_license_key
INSIGHTFINDER_PROJECT_NAME=your_project_name
# Control resolved alert streaming
STREAM_RESOLVED_ALERTS=false
```

## Use Cases

### Scenario 1: Full Alert Tracking (Default)
Use `stream_resolved_alerts = true` when you want to track both problem and resolution events in InsightFinder for complete incident lifecycle visibility.

### Scenario 2: Problem-Only Tracking
Use `stream_resolved_alerts = false` when you:
- Only want to see when problems occur, not when they resolve
- Want to reduce data volume in InsightFinder
- Have external resolution tracking but still want incident investigation to work

## API Endpoint Behavior

### With `stream_resolved_alerts = true`
```
PROBLEM Event → Send to /api/v1/customprojectrawdata
RESOLVED Event → Send to /api/v1/customprojectrawdata + Call incident investigation API
```

### With `stream_resolved_alerts = false`
```
PROBLEM Event → Send to /api/v1/customprojectrawdata
RESOLVED Event → Skip /api/v1/customprojectrawdata, Only call incident investigation API
```

## Example Configurations

### Example 1: Production Environment (Full Tracking)
```ini
# config/insightfinder/production.ini
[insightfinder]
base_url = https://app.insightfinder.com
username = prod_user
license_key = prod_license_key
project_name = production_monitoring
system_name = production_zabbix

[project_settings]
stream_resolved_alerts = true  # Track complete incident lifecycle
```

### Example 2: Development Environment (Problem Only)
```ini
# config/insightfinder/development.ini
[insightfinder]
base_url = https://stg.insightfinder.com
username = dev_user
license_key = dev_license_key
project_name = dev_monitoring
system_name = dev_zabbix

[project_settings]
stream_resolved_alerts = false  # Only track problems, not resolutions
```

## Testing the Configuration

You can test your configuration using the test webhook endpoint:

```bash
curl -X POST "http://localhost:80/webhook/test" \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "event_value": "0",
    "host_name": "test-host",
    "event_date": "2025-01-15",
    "event_time": "10:30:00",
    "trigger_name": "Test Alert"
  }'
```

Check the logs to see if the resolved alert was skipped or sent based on your configuration.

## Verification

To verify your configuration is working:

1. Check the server status endpoint: `GET /status`
2. Look for the `stream_resolved_alerts` setting in the configuration details
3. Monitor logs when processing resolved events to see if they're being skipped

## Logging

When `stream_resolved_alerts = false`, you'll see log messages like:
```
Skipping resolved alert streaming for host: test-host (stream_resolved_alerts=False)
Event is RESOLVED, calling incident investigation API only...
```

When `stream_resolved_alerts = true`, you'll see:
```
Event is RESOLVED, calling incident investigation API...
Successfully sent alert for host: test-host
```
