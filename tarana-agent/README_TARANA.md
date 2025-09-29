# Tarana Agent for InsightFinder

This agent collects metrics and logs from Tarana wireless devices and sends the Collected Metrics

The agent collects KPI metrics from Tarana devices based on your configuration. Default metrics include:

- **RF Range** (`RF-Range`)
- **Path Loss** (`Path-Loss`)
- **System Uptime** (`System-Uptime`)
- **Connection Uptime** (`Connection-Uptime`)
- **RX Signal Levels** for radios 0-3 (`RX-Signal-Radio-0` through `RX-Signal-Radio-3`)
- **Downlink SNR** (`DL-SNR`)
- **Uplink SNR** (`UL-SNR`)

**Configurable Metrics**: All metrics are fully configurable through the `tarana.kpis` section in config.yaml. You can:
- Add new KPI paths that Tarana supports
- Customize metric names to match your naming conventions
- Remove metrics you don't need to reduce data volumender for monitoring and analysis.

## Features

- **Automatic Authentication**: Handles login and token refresh for Tarana API
- **Device Discovery**: Automatically discovers all Tarana devices in configured regions
- **Metrics Collection**: Collects KPI metrics from all discovered devices
- **Logs Collection**: Collects alarms and events from Tarana systems
- **Batch Processing**: Efficiently processes large numbers of devices and metrics
- **Error Handling**: Robust error handling with retry mechanisms
- **Configurable**: Flexible configuration for different environments

## Prerequisites

- Go 1.19 or higher
- Access to Tarana portal API
- InsightFinder account with appropriate projects created

## Installation

1. Clone or download this repository
2. Navigate to the tarana-agent directory
3. Install dependencies:
   ```bash
   go mod download
   ```

## Configuration

1. Copy the sample configuration file:
   ```bash
   cp configs/config.yaml.sample configs/config.yaml
   ```

2. Edit `configs/config.yaml` with your settings:

### Tarana Configuration
- `base_url`: Tarana portal base URL (default: https://portal.tcs.taranawireless.com)
- `username`: Your Tarana portal username
- `password`: Your Tarana portal password  
- `region_ids`: Array of region IDs to monitor
- `kpis`: Map of KPI paths to desired metric names (see KPI Configuration below)
- `verify_ssl`: Whether to verify SSL certificates (recommended: true)
- `max_concurrent_requests`: Maximum concurrent API requests (default: 10)
- `token_refresh_threshold`: Seconds before token expiry to refresh (default: 300)

### InsightFinder Configuration
- `server_url`: InsightFinder server URL
- `username`: InsightFinder username
- `license_key`: InsightFinder license key
- `metrics_project_name`: Name for metrics project
- `logs_project_name`: Name for logs project
- `sampling_interval`: Data collection interval in seconds (default: 300)
- `cloud_type`: Cloud type identifier (e.g., "OnPremise", "AWS")
- `instance_type`: Instance type identifier
- `is_container`: Set to true if running in container

### KPI Configuration
Configure which KPIs to collect and their metric names in the `tarana.kpis` section:

```yaml
tarana:
  kpis:
    "/connections/connection/state/rf-range": "RF-Range"
    "/connections/connection/state/path-loss": "Path-Loss"
    "/connections/connection/system/state/uptime": "System-Uptime"
    "/connections/connection/state/uptime": "Connection-Uptime"
    "/connections/connection/radios/radio[id=0]/state/rx-signal-level/min": "RX-Signal-Radio-0"
    "/connections/connection/radios/radio[id=1]/state/rx-signal-level/min": "RX-Signal-Radio-1"
    "/connections/connection/radios/radio[id=2]/state/rx-signal-level/min": "RX-Signal-Radio-2"
    "/connections/connection/radios/radio[id=3]/state/rx-signal-level/min": "RX-Signal-Radio-3"
    "/connections/connection/state/dl-snr": "DL-SNR"
    "/connections/connection/state/ul-snr": "UL-SNR"
```

**Benefits of configurable KPIs:**
- Add or remove metrics without code changes
- Customize metric names for better organization
- Easy to adapt to new Tarana KPI endpoints
- Control data volume by selecting only needed metrics

### KPI Availability Handling

The agent intelligently handles varying KPI availability:

- **Dynamic Processing**: Only processes KPIs that are actually present in the API response
- **No Missing Data**: Skips unavailable KPIs instead of creating empty metrics
- **Unavailability Tracking**: Logs information about KPIs that couldn't be retrieved
- **Per-Device Granularity**: Each device may have different available KPIs

**Example Scenarios:**
- Device offline: No KPIs available for that device
- Partial connectivity: Only some KPIs available
- Configuration mismatch: Requested KPIs not supported by device

The agent will only send metrics for KPIs that are actually returned by the Tarana API, ensuring data accuracy and preventing false zero values.

### Agent Configuration
- `log_level`: Logging level (DEBUG, INFO, WARN, ERROR)
- `timezone`: Timezone for timestamps (default: UTC)

## Running the Agent

### Development Mode
```bash
go run main.go
```

### Production Mode
```bash
# Build the binary
go build -o tarana-agent main.go

# Run the agent
./tarana-agent
```

### Docker (Optional)
```bash
# Build Docker image
docker build -t tarana-agent .

# Run with mounted config
docker run -v /path/to/config:/app/configs tarana-agent
```

## Collected Metrics

The agent collects the following KPI metrics from Tarana devices:

- **RF Range** (`RF-RANGE`)
- **Path Loss** (`PATH-LOSS`)
- **System Uptime** (`UPTIME`)
- **Connection Uptime** (`UPTIME`)
- **RX Signal Levels** for radios 0-3 (`MIN`)
- **Downlink SNR** (`DL-SNR`)
- **Uplink SNR** (`UL-SNR`)

**Metric Naming**: The agent extracts the last part of each KPI path and converts it to uppercase. For example:
- `/connections/connection/state/dl-snr` becomes `DL-SNR`
- `/connections/connection/state/rf-range` becomes `RF-RANGE`

### Metric Metadata
Each metric includes:
- `instanceName`: Device hostname
- `componentName`: Device type (e.g., "RN", "BN")
- `ip`: Device IP address
- `timestamp`: Unix timestamp in milliseconds

## Collected Logs

The agent collects alarm/event logs with time-based filtering and deduplication:

- **Time-based filtering**: Only alarms from the last minute are collected
- **Deduplication**: Tracks the last sent alarm timestamp to avoid resending
- **Watermark tracking**: Maintains session state for alarm processing
- Device alarms and errors
- Status changes (NACK alarms)
- System events
- Threshold violations

### Log Data Format

Logs are formatted as JSON objects (similar to positron-agent) with structured data fields:

```json
{
  "timestamp": 1703123456789,
  "tag": "device_serial_123",
  "componentName": "TaranaDevice",
  "instanceName": "device_serial_123", 
  "data": {
    "message": "Alarm text description",
    "alarm_id": "ALARM123",
    "status": "ACTIVE",
    "severity": 3,
    "category": "SYSTEM",
    "device_id": "device_serial_123",
    "device_hostname": "tarana-device-01",
    "device_ip": "192.168.1.100",
    "device_type": "TDD",
    "time_created": 1703123400000,
    "time_cleared": 0,
    "instance_name": "device_serial_123",
    "component_name": "TaranaDevice"
  }
}
```

### Log Metadata
Each log entry includes:
- Device information (hostname, IP, serial number)
- Alarm details (ID, text, severity, category)  
- Timestamps (creation, clearance)
- Regional and site information

## API Integration

### Tarana APIs Used

1. **Authentication**
   - `POST /api/tcs/v1/user-auth/login` - Initial login with basic auth
   - `POST /api/tcs/v1/user-auth/refresh` - Token refresh using cookies
   
   **Note**: The refresh API may not return a new refresh token in the response. The agent handles this by preserving the existing refresh token when a new one isn't provided.

2. **Device Discovery**
   - `POST /api/nqs/v1/regions/devices/search` - Get device list

3. **Metrics Collection**
   - `POST /api/tmq/v5/radios/kpi/latest-per-radio` - Get device metrics

4. **Logs Collection**
   - `POST /api/ttm/v1/radios/alarm/details` - Get alarms/events
   
   **Alarm Filtering**: The agent implements intelligent alarm filtering to prevent duplicates and reduce noise:
   - Only processes alarms created in the last minute
   - Maintains a watermark of the last processed alarm timestamp
   - Skips alarms that have already been sent to InsightFinder

## Troubleshooting

### Common Issues

1. **Authentication Failures**
   - Verify username/password in config
   - Check network connectivity to Tarana portal
   - Ensure account has API access permissions
   - Monitor logs for token refresh patterns
   
   **Token Refresh Issues**: If you see frequent re-login attempts, the refresh token may be expiring or the API behavior may have changed. Enable DEBUG logging to see detailed token refresh information.

2. **No Devices Found**
   - Verify region_ids in configuration
   - Check that regions contain devices
   - Ensure account has access to specified regions

3. **InsightFinder Connection Issues**
   - Verify server_url, username, and license_key
   - Check project names exist or will be created
   - Ensure network connectivity to InsightFinder

4. **High Memory Usage**
   - Reduce batch sizes in worker.go
   - Increase sampling_interval
   - Limit concurrent requests

### Logging

The agent provides detailed logging. Set `log_level: "DEBUG"` in config for maximum verbosity.

Log files show:
- Authentication status
- Device discovery results  
- Metrics collection statistics
- InsightFinder transmission status
- Error details and retry attempts

### Monitoring

The agent tracks internal statistics:
- Total devices discovered
- Metrics collected and sent
- Logs collected and sent
- Error counts
- Collection cycle timing

## Performance Tuning

### For Large Deployments
- Increase `max_concurrent_requests` (but watch API rate limits)
- Adjust batch sizes in worker.go
- Increase `sampling_interval` for less frequent collection
- Monitor memory usage and adjust accordingly

### For High-Frequency Collection
- Decrease `sampling_interval`
- Optimize batch sizes
- Consider running multiple agent instances for different regions

## Security Considerations

- Store credentials securely
- Use environment variables for sensitive config
- Enable SSL verification (`verify_ssl: true`)
- Regularly rotate API credentials
- Monitor agent logs for security events

## Support

For issues or questions:
1. Check logs for error messages
2. Verify configuration settings
3. Test network connectivity
4. Contact InsightFinder support if needed

## License

[Include your license information here]