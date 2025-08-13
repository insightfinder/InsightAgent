# Mimosa InsightFinder Agent

This agent collects metrics data from Mimosa devices and sends it to InsightFinder for monitoring and analysis.

## Overview

The Mimosa agent connects to Mimosa Cloud platform, retrieves device metrics in batches, and forwards the data to InsightFinder. It supports configurable batch processing, multiple data points collection, and efficient API usage to minimize the number of requests.

## Features

- **Batch Processing**: Efficiently collects metrics from multiple devices in single API calls
- **Configurable Data Points**: Collect multiple historical data points per metric (not just the latest)
- **Device Filtering**: Option to limit the number of devices for testing or performance
- **Component Name Mapping**: Configurable component names for better organization in InsightFinder
- **Robust Error Handling**: Fallback mechanisms and retry logic
- **Debug Output**: Saves collected data to JSON files for inspection

## Prerequisites

- Python 3.6+
- Access to Mimosa Cloud platform
- InsightFinder account and project setup
- Required Python packages (see `requirements.txt`)

## Installation

1. **Clone or download the agent files**
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Set up configuration**:
   ```bash
   cp conf.d/config.ini.template conf.d/config.ini
   ```

## Configuration

Edit `conf.d/config.ini` with your specific settings:

### Mimosa Settings (`[mimosa]` section)

| Parameter | Description | Required | Default | Example |
|-----------|-------------|----------|---------|---------|
| `mimosa_uri` | Mimosa Cloud platform URL | Yes | - | `https://cloud.mimosa.co` |
| `username` | Mimosa account username | Yes | - | `your_username` |
| `password` | Mimosa account password | Yes | - | `your_password` |
| `verify_certs` | SSL certificate verification | No | `True` | `False` |
| `network_id` | Mimosa network ID | No | `6078` | `6078` |
| `action_names` | Comma-separated list of metrics to collect | No | `Mimosa_B5_UL_Rate,Mimosa_B5_DL_Rate` | `Mimosa_B5_UL_Rate,Mimosa_B5_DL_Rate,Mimosa_B5_Signal_Strength` |
| `max_devices` | Limit number of devices (0 = no limit) | No | `0` | `100` |
| `api_batch_size` | Devices per API call | No | `25` | `50` |
| `data_points_count` | Number of historical data points to collect | No | `1` | `5` |

### Agent Settings (`[agent]` section)

| Parameter | Description | Required | Default | Example |
|-----------|-------------|----------|---------|---------|
| `default_component_name` | Component name for InsightFinder | No | `""` | `mimosa_network` |
| `thread_pool` | Number of worker threads | No | `20` | `5` |
| `his_time_range` | Historical time range (not supported) | No | `""` | - |

### InsightFinder Settings (`[insightfinder]` section)

| Parameter | Description | Required | Default | Example |
|-----------|-------------|----------|---------|---------|
| `user_name` | InsightFinder username | Yes | - | `your_username` |
| `license_key` | InsightFinder license key | Yes | - | `your_license_key` |
| `project_name` | InsightFinder project name | Yes | - | `mimosa_metrics` |
| `system_name` | System name (optional) | No | `""` | `production` |
| `project_type` | Project type | No | `metric` | `metric` |
| `sampling_interval` | Data collection interval | No | `15s` | `60s` |
| `run_interval` | Agent run interval | No | `60s` | `60s` |
| `if_url` | InsightFinder URL | No | `https://app.insightfinder.com` | - |

## Usage

### Basic Usage

Run the agent with default settings:
```bash
python getmessages_mimosa.py
```

### Command Line Options

```bash
python getmessages_mimosa.py [options]

Options:
  -c, --config PATH    Path to config directory (default: conf.d)
  -v, --verbose        Enable verbose logging
  -q, --quiet          Only show warnings and errors
  -t, --testing        Testing mode (don't send data to InsightFinder)
```

### Testing Mode

To test the configuration without sending data to InsightFinder:
```bash
python getmessages_mimosa.py -t -v
```

This will:
- Enable verbose logging
- Collect metrics from Mimosa
- Save data to JSON files
- Show what would be sent to InsightFinder
- Skip actual data transmission

## Data Collection Behavior

### Single Data Point (Default)
When `data_points_count = 1`:
- Collects the latest/most recent data point for each metric
- Minimal data transfer and processing

### Multiple Data Points
When `data_points_count = 5`:
- Collects the last 5 data points for each metric
- Each data point includes its original timestamp
- Useful for historical analysis and trend detection, or if metrics are not updated every minute

### API Efficiency
- **Batch Processing**: Groups multiple devices into single API calls
- **Concurrent Processing**: Uses thread pools for parallel requests
- **Fallback Logic**: Switches to individual device calls if batch fails
- **Rate Limiting**: Configurable batch sizes to avoid overwhelming API

## Output Files

The agent creates these files for debugging and inspection:

- `mimosa_metrics_data.json` - Raw metrics data from Mimosa API
- `mimosa_insightfinder_data.json` - Formatted data sent to InsightFinder
- `cache/cache.db` - SQLite cache for device aliases

## Metrics Collected

The agent collects metrics specified in the `action_names` configuration. Common metrics include:

- `Mimosa_B5_UL_Rate` - Upload rate
- `Mimosa_B5_DL_Rate` - Download rate  
- `Mimosa_B5_Signal_Strength` - Signal strength
- `Mimosa_B5_Temperature` - Device temperature
- `Mimosa_B5_Voltage` - Power voltage

Each metric includes:
- Device name and ID
- Metric value and timestamp
- Device metadata (model, IP, MAC, software version)

## Troubleshooting

### Common Issues

1. **Login Failed**
   - Check username/password in config
   - Verify Mimosa Cloud access
   - Check network connectivity

2. **No Devices Found**
   - Verify `network_id` setting
   - Check device permissions in Mimosa Cloud
   - Ensure devices are online and reporting

3. **API Timeouts**
   - Reduce `api_batch_size`
   - Decrease `max_devices` for testing
   - Check network latency to Mimosa Cloud

4. **InsightFinder Errors**
   - Verify license key and project name
   - Check project type is set to `metric`
   - Ensure project exists in InsightFinder

### Debug Steps

1. **Enable verbose logging**:
   ```bash
   python getmessages_mimosa.py -v
   ```

2. **Use testing mode**:
   ```bash
   python getmessages_mimosa.py -t -v
   ```

3. **Check output files**:
   - Review `mimosa_metrics_data.json` for raw API data
   - Check `mimosa_insightfinder_data.json` for formatted output

4. **Reduce scope for testing**:
   ```ini
   max_devices = 5
   api_batch_size = 1
   data_points_count = 1
   ```

## Performance Tuning

### For Large Deployments
```ini
api_batch_size = 50        # More devices per API call
max_devices = 0            # No device limit
data_points_count = 1      # Single data point for efficiency
thread_pool = 10           # More concurrent threads
```

### For Detailed Analysis
```ini
api_batch_size = 25        # Moderate batch size
data_points_count = 5      # Multiple historical points
sampling_interval = 300s   # 5-minute intervals
```

### For Testing/Development
```ini
max_devices = 10           # Limit devices
api_batch_size = 5         # Small batches
data_points_count = 1      # Single points
```

## Security Notes

- Store credentials securely in `conf.d/config.ini`
- The config file is excluded from git by default
- Use `verify_certs = True` in production environments
- Consider using environment variables for sensitive data

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review log files with verbose mode enabled
3. Verify configuration parameters
4. Test with minimal settings first

## License

This agent is part of the InsightFinder platform integration tools.
