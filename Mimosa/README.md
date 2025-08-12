# Mimosa Agent for InsightFinder

This agent collects metrics from Mimosa wireless devices and sends them to InsightFinder for monitoring and analysis.

## Features

- Secure login to Mimosa devices via REST API
- Configurable metric collection from various device endpoints
- Real-time metric streaming to InsightFinder
- SSL certificate verification support
- Robust error handling and logging
- Multi-threaded data collection

## Prerequisites

- Python 3.6 or higher
- Network access to Mimosa device(s)
- Valid InsightFinder account with license key
- Mimosa device with API access enabled

## Installation

1. Clone or download this agent directory
2. Install required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. Copy the configuration template:
   ```bash
   cp conf.d/config.ini.template conf.d/config.ini
   ```

2. Edit `conf.d/config.ini` with your specific settings:

### Mimosa Device Settings
```ini
[mimosa]
mimosa_uri = http://192.168.1.100  # Your Mimosa device IP/hostname
username = admin                   # Mimosa device username
password = your_password          # Mimosa device password
verify_certs = True               # SSL certificate verification
```

### Metrics Configuration
Define which metrics to collect in the `[metrics]` section. Format:
```ini
metric_name = endpoint:value_path:params
```

Examples:
```ini
[metrics]
# Signal strength
rssi = /api/stats:wireless.rssi
snr = /api/stats:wireless.snr

# Throughput
tx_rate = /api/stats:throughput.tx_rate
rx_rate = /api/stats:throughput.rx_rate

# System health
cpu_usage = /api/system:cpu.usage_percent
memory_usage = /api/system:memory.usage_percent
```

### InsightFinder Settings
```ini
[insightfinder]
user_name = your_if_username
license_key = your_if_license_key
project_name = Mimosa_Metrics
project_type = metric
sampling_interval = 15s
```

## Usage

Run the agent:
```bash
python getmessages_mimosa.py
```

### Command Line Options

- `-c, --config`: Path to config directory (default: ./conf.d)
- `-v, --verbose`: Enable verbose logging
- `-q, --quiet`: Only show warnings and errors
- `-t, --testing`: Test mode (doesn't send data to InsightFinder)

Examples:
```bash
# Verbose mode
python getmessages_mimosa.py -v

# Test mode (no data sent)
python getmessages_mimosa.py -t

# Custom config directory
python getmessages_mimosa.py -c /path/to/config
```

## Supported Metrics

The agent can collect various metrics from Mimosa devices, including:

### Wireless Metrics
- RSSI (Received Signal Strength Indicator)
- SNR (Signal-to-Noise Ratio)
- Noise floor
- Link quality
- Frequency information

### Throughput Metrics
- TX/RX data rates
- Byte counters
- Packet counters
- Error rates

### System Metrics
- CPU usage
- Memory usage
- Temperature
- Uptime
- Voltage levels

### Network Interface Metrics
- Ethernet interface statistics
- Wireless interface statistics
- VLAN statistics

## API Endpoints

Common Mimosa API endpoints that can be used:

- `/api/stats` - General device statistics
- `/api/system` - System information and health
- `/api/interfaces` - Network interface details
- `/api/wireless` - Wireless-specific metrics
- `/api/config` - Device configuration (read-only)

## Troubleshooting

### Common Issues

1. **Authentication Failed**
   - Verify username and password in config
   - Check if API access is enabled on the Mimosa device
   - Ensure device is accessible over the network

2. **SSL Certificate Errors**
   - Set `verify_certs = False` if using self-signed certificates
   - Ensure proper CA certificates are installed

3. **Network Connectivity**
   - Verify the Mimosa device URI is correct
   - Check firewall rules and network access
   - Test connectivity: `ping <device_ip>`

4. **Missing Metrics**
   - Check if the API endpoint exists on your device
   - Verify the value_path in metric configuration
   - Enable verbose logging to see detailed errors

### Logging

The agent provides detailed logging. Use `-v` flag for verbose output:
```bash
python getmessages_mimosa.py -v
```

Log levels:
- INFO: General operation information
- DEBUG: Detailed debugging information (use with -v)
- WARNING: Non-critical issues
- ERROR: Critical errors

## Data Format

Metrics are sent to InsightFinder in the following format:
```json
{
  "instanceName": "mimosa_001",
  "componentName": "mimosa_device", 
  "metricName": "rssi",
  "data": -45.5,
  "timestamp": 1625097600000
}
```

## Security Considerations

- Store credentials securely
- Use HTTPS when possible
- Enable SSL certificate verification in production
- Restrict network access to authorized hosts only
- Regularly update device firmware and agent dependencies

## Support

For issues related to:
- **Mimosa devices**: Contact Mimosa support
- **InsightFinder**: Contact InsightFinder support  
- **This agent**: Check logs and configuration first

## License

This agent is provided as-is for use with InsightFinder monitoring platform.
