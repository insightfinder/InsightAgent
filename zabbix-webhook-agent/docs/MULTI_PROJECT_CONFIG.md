# Multi-Project Configuration Guide

This document explains how to configure the Zabbix Webhook Agent to support multiple InsightFinder projects using `.ini` configuration files.

## Configuration Structure
### Directory Structure

```
config/
├── insightfinder/
│   ├── default.ini      # Default configuration
│   ├── production.ini   # Production environment
│   ├── staging.ini      # Staging environment
│   └── project1.ini     # Custom project configuration
```

### INI File Format

Each `.ini` file contains two sections:

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
```

## Configuration Parameters

### InsightFinder Section

- `base_url`: InsightFinder base URL (default: https://app.insightfinder.com)
- `username`: InsightFinder username
- `password`: InsightFinder password (optional, for session management)
- `license_key`: InsightFinder license key
- `project_name`: InsightFinder project name
- `system_name`: System name for the project (used in project creation)

### Project Settings Section

- `instance_type`: Type of instance (default: Zabbix)
- `project_cloud_type`: Cloud type for the project (default: Zabbix)
- `data_type`: Type of data being sent (default: Log)
- `insight_agent_type`: Agent type (default: Custom)
- `sampling_interval`: Sampling interval in seconds (default: 60)
- `sampling_interval_in_seconds`: Sampling interval (default: 60)

## Usage

### API Endpoints

#### 1. List All Configurations

```bash
GET /configs
```

Returns all available configurations with their details.

#### 2. Get Specific Configuration

```bash
GET /configs/{config_name}
```

Returns details for a specific configuration.

#### 3. Reload Configurations

```bash
POST /configs/reload
```

Reloads all configurations from disk.

#### 4. Send Webhook with Specific Configuration

```bash
POST /webhook/zabbix/{config_name}
```

Process webhook using a specific configuration.

#### 5. Send Webhook with Dynamic Configuration

```bash
POST /webhook/zabbix
```

Include `config_name` in the request body to specify which configuration to use:

```json
{
  "config_name": "production",
  "event_id": "123",
  "host_name": "server01",
  ...
}
```

### Examples

#### Example 1: Using Default Configuration

```bash
curl -X POST "http://localhost:8000/webhook/zabbix" \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "123",
    "host_name": "server01",
    "event_name": "High CPU usage"
  }'
```

#### Example 2: Using Specific Configuration

```bash
curl -X POST "http://localhost:8000/webhook/zabbix/production" \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "123",
    "host_name": "server01",
    "event_name": "High CPU usage"
  }'
```

#### Example 3: Dynamic Configuration Selection

```bash
curl -X POST "http://localhost:8000/webhook/zabbix" \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "config_name": "staging",
    "event_id": "123",
    "host_name": "server01",
    "event_name": "High CPU usage"
  }'
```

## Migration from Legacy Configuration

The server maintains backward compatibility with `.env` configuration files. If no `.ini` configurations are found, the server will fall back to using the legacy `.env` settings.

### Legacy Environment Variables (still supported)

```env
INSIGHTFINDER_BASE_URL=https://app.insightfinder.com
INSIGHTFINDER_USERNAME=demo_user
INSIGHTFINDER_PASSWORD=demo_password
INSIGHTFINDER_LICENSE_KEY=demo_license_key
INSIGHTFINDER_PROJECT_NAME=demo_project
```

## Configuration Management

### Adding New Configurations

1. Create a new `.ini` file in `config/insightfinder/`
2. Follow the format shown above
3. Reload configurations using the API or restart the server

### Updating Configurations

1. Edit the appropriate `.ini` file
2. Call the reload endpoint: `POST /configs/reload`

### Configuration Validation

The server validates configurations on startup and when reloading. Invalid configurations are logged and skipped.

## Security Considerations

- Store sensitive data (passwords, license keys) securely
- Use environment variables for sensitive configuration if needed
- Restrict access to configuration files
- Use API authentication for all endpoints

## Troubleshooting

### Common Issues

1. **Configuration not found**: Ensure the `.ini` file exists and is properly formatted
2. **Permission errors**: Check file permissions on configuration directory
3. **Invalid format**: Validate INI syntax and required sections
4. **Missing credentials**: Ensure all required fields are present

### Checking Configuration Status

Use the status endpoint to check configuration health:

```bash
curl -X GET "http://localhost:8000/status" \
  -H "X-API-Key: your_api_key"
```

This will show:
- Available configurations
- Configuration summary
- Health status

## Zone Name Configuration

The server now supports using Zabbix hostgroup names as zone names in InsightFinder. The zone name is determined as follows:

1. **Primary**: Uses `hostgroup_name` field from the Zabbix webhook data
2. **Fallback**: Uses `host_group` field if `hostgroup_name` is not available
3. **Default**: Uses "DefaultZone" if neither field is provided or if they are empty

### Zabbix Configuration

To include hostgroup information in your Zabbix webhook, configure your Zabbix media script to send the following additional fields:

```javascript
// In your Zabbix media script, add:
var payload = {
    // ...existing fields...
    "hostgroup_name": "{HOST.GROUPS}",  // Preferred field
    "host_group": "{HOST.GROUP}",       // Alternative field
    // ...other fields...
};
```

### Example Webhook Data

```json
{
  "event_id": "123456",
  "host_name": "web-server-01",
  "hostgroup_name": "Web Servers",
  "event_name": "High CPU usage",
  // ...other fields...
}
```

This will result in "Web Servers" being used as the `zoneName` in InsightFinder.
