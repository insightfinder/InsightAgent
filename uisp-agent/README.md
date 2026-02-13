# UISP to InsightFinder Integration

Agent for collecting signal metrics from UISP devices and sending them to InsightFinder.

## Overview

Monitor your UISP network infrastructure with AI-powered anomaly detection. This agent automatically:

1. **Discovers** active 60GHz devices in your UISP network
2. **Collects** signal strength metrics (local/remote, 5GHz/60GHz)
3. **Detects gaps** in metrics data with human-readable warnings
4. **Transforms** data to InsightFinder's metric format
5. **Sends** metrics to InsightFinder

### Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting) ⭐
- [Automation](#automation--scheduling)
- [Development](#development--testing)
- [Best Practices](#best-practices)
- [API Reference](#api-reference)

## Prerequisites

- Python 3.10 or higher
- UISP NMS access with API token
- InsightFinder account with license key

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create .env file with your credentials
cat > .env << EOF
UISP_URL="https://accessparks.unmsapp.com"
UISP_API_TOKEN="your-api-token"
INSIGHTFINDER_BASE_URL="https://app.insightfinder.com"
INSIGHTFINDER_USER_NAME="your-username"
INSIGHTFINDER_LICENSE_KEY="your-license-key"
INSIGHTFINDER_PROJECT_NAME="uisp-metrics"
INSIGHTFINDER_SYSTEM_NAME="your-system-name"
INSIGHTFINDER_SAMPLING_INTERVAL="5"  # in minutes
EOF

# 3. Test with dry run
python send_metrics.py --dry-run -v

# 4. Send metrics to InsightFinder
python send_metrics.py
```

For detailed setup, see [Installation](#installation) below.

## Installation

1. **Clone the repository**

   ```bash
   cd /path/to/your/workspace
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**

   Create a `.env` file in the project root:

   ```bash
   # UISP Configuration
   UISP_URL="https://accessparks.unmsapp.com"
   UISP_API_TOKEN="your-uisp-api-token"

   # InsightFinder Configuration
   INSIGHTFINDER_BASE_URL="https://app.insightfinder.com"
   INSIGHTFINDER_USER_NAME="your-username"
   INSIGHTFINDER_LICENSE_KEY="your-license-key"
   INSIGHTFINDER_PROJECT_NAME="uisp-metrics"
   INSIGHTFINDER_SYSTEM_NAME="your-system-name"
   INSIGHTFINDER_SAMPLING_INTERVAL="5"
   ```

### Configuration Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `UISP_URL` | UISP NMS base URL | `https://accessparks.unmsapp.com` |
| `UISP_API_TOKEN` | UISP API authentication token | `xxxxxx-xxx` |
| `INSIGHTFINDER_BASE_URL` | InsightFinder instance URL | `https://app.insightfinder.com` |
| `INSIGHTFINDER_USER_NAME` | InsightFinder username | `user` |
| `INSIGHTFINDER_LICENSE_KEY` | InsightFinder license key | Your license key from Account Profile |
| `INSIGHTFINDER_PROJECT_NAME` | Target project name | `uisp-metrics` |
| `INSIGHTFINDER_SYSTEM_NAME` | System identifier | `UISP` |
| `INSIGHTFINDER_SAMPLING_INTERVAL` | Metric sampling interval in minutes | `5` (5 minutes) |

## Usage

### View UISP Device Metrics

List all active 60GHz devices:

```bash
python get_metrics.py --list-all
```

View detailed metrics for all devices:

```bash
python get_metrics.py
```

View metrics for specific device:

```bash
python get_metrics.py -d "Device-Name"
```

Customize time range and sampling:

```bash
python get_metrics.py --period 1h --num-points 10 --sample-interval 5m
```

### Send Metrics to InsightFinder

**Basic usage** (last 1 hour of data, auto-creates project):

```bash
python send_metrics.py
```

**Common scenarios:**

```bash
# Send last 10 minutes of data
python send_metrics.py --period 10m

# Send last 2 hours
python send_metrics.py --period 2h

# Limit to first 5 devices (useful for testing)
python send_metrics.py -n 5

# Preview without sending (dry run)
python send_metrics.py --dry-run

# Verbose mode with human-readable timestamps and gap detection
python send_metrics.py -v

# Adjust sampling interval (default: from .env)
python send_metrics.py --sample-interval 1m
```

**Debugging data gaps:**

```bash
# See detailed gap warnings with timestamps
python send_metrics.py -v --period 2h

# Test single device with verbose output
python send_metrics.py -n 1 -v --dry-run
```

### Command-Line Options

**send_metrics.py** (Main script):

| Option | Description | Default |
|--------|-------------|--------|
| `-n, --limit N` | Limit to first N devices | All devices |
| `--period PERIOD` | Time period to fetch (e.g., `10m`, `1h`, `2h`, `7d`) | `1h` |
| `--num-points N` | Limit data points per device | All points |
| `--sample-interval INTERVAL` | Sample interval (e.g., `1m`, `5m`) | From `.env` |
| `--create-project` | Auto-create InsightFinder project | Enabled |
| `--no-create-project` | Disable auto-creation | - |
| `--dry-run` | Preview without sending | - |
| `-v, --verbose` | Enable debug logging with human-readable timestamps | - |

**get_metrics.py** (For testing/viewing data):

| Option | Description | Default |
|--------|-------------|--------|
| `-n, --limit N` | Limit to first N devices | All devices |
| `--period PERIOD` | Time period (e.g., `10m`, `1h`, `7d`) | `10m` |
| `--num-points N` | Number of data points to display | All points |
| `--sample-interval INTERVAL` | Sampling interval (e.g., `1m`, `5m`) | `1m` |
| `--list-all` | List all devices without detailed metrics | - |
| `-d, --device NAME` | Filter by device name or ID | - |

## Data Format

### Metric Naming Convention

UISP metrics are transformed to InsightFinder format with consistent naming:

| UISP Metric | InsightFinder Metrics |
|-------------|----------------------|
| `signal` | `signal_avg`, `signal_max` |
| `remoteSignal` | `remote_signal_avg`, `remote_signal_max` |
| `signal60g` | `signal_60ghz_avg`, `signal_60ghz_max` |
| `remoteSignal60g` | `remote_signal_60ghz_avg`, `remote_signal_60ghz_max` |

### Instance Name Sanitization

Device names are automatically sanitized to comply with InsightFinder requirements:

- Replace: `_` → `-`
- Remove: `@`, `#`, `:`

**Example:** `ETHO-Office_HE-PTP_to_BoatDock` → `ETHO-Office-HE-PTP-to-BoatDock`

### Example Data Flow

**Input (from UISP API):**

```json
{
  "signal": {
    "avg": [
      {"x": 1707580800000, "y": -44.0},
      {"x": 1707580860000, "y": -45.0}
    ],
    "max": [
      {"x": 1707580800000, "y": -42.0},
      {"x": 1707580860000, "y": -43.0}
    ]
  },
  "signal60g": {
    "avg": [
      {"x": 1707580800000, "y": -30.0}
    ],
    "max": [
      {"x": 1707580800000, "y": -28.0}
    ]
  }
}
```

**Output (to InsightFinder v2 API):**

```json
{
  "userName": "your-username",
  "licenseKey": "your-license-key",
  "data": {
    "projectName": "uisp-metrics",
    "userName": "your-username",
    "iat": "custom",
    "ct": "PrivateCloud",
    "idm": {
      "AP-Site1": {
        "in": "AP-Site1",
        "dit": {
          "1707580800000": {
            "t": 1707580800000,
            "metricDataPointSet": [
              {"m": "signal_avg", "v": 44.0},
              {"m": "signal_max", "v": 42.0},
              {"m": "signal_60ghz_avg", "v": 30.0},
              {"m": "signal_60ghz_max", "v": 28.0}
            ]
          }
        }
      }
    }
  }
}
```

**Note:** Signal values are converted to absolute (positive) values. The v2 API uses a nested structure with:

- `idm`: Instance Data Map containing all instances
- `dit`: Data in Timestamp map for each instance
- `metricDataPointSet`: Array of metric name/value pairs

## Automation / Scheduling

### Using Python Scheduler

The included `cron.py` script provides a cross-platform Python-based scheduler that automatically runs at the interval specified in your `.env` file.

**Features:**

- ✅ Reads `INSIGHTFINDER_SAMPLING_INTERVAL` from `.env` automatically (in minutes)
- ✅ Fetches only the latest data point with overlapping windows (prevents gaps)
- ✅ Cross-platform (Linux, macOS, Windows)
- ✅ Logs to stdout (can be redirected as needed)
- ✅ Graceful shutdown on Ctrl+C

**Usage:**

```bash
# Start the scheduler (runs in foreground)
python cron.py
```

The scheduler will:

- Run `send_metrics.py --num-points 1 --period <2x_interval>` at regular intervals
- Use 2x sampling interval for fetch period (e.g., 60s interval → fetch last 2 minutes)
- Log all output to stdout (redirect to file if needed)

**Example output:**

```
============================================================
UISP Metrics Scheduler Configuration
============================================================
Sampling Interval: 5 minutes (300 seconds)
Fetch Period: 10m (2x interval)
Device Limit: All devices
Verbose Mode: Disabled
Schedule: {'minute': '*/5'}
Max Instances: 1 (prevents overlap)
Coalesce: True (combines missed runs)
Misfire Grace: 300 seconds
Job Timeout: 300 seconds
Python: /path/to/uisp-agent/.venv/bin/python3
Script: /path/to/uisp-agent/send_metrics.py
Arguments: --num-points 1 --period 10m
============================================================

Scheduler will run send_metrics.py every 5 minutes
Each run fetches the latest data point from a 10m window

Press Ctrl+C to stop the scheduler
============================================================

Running initial job execution...
```

## Project Structure

```
uisp-agent/
├── .env                              # Environment configuration
├── requirements.txt                  # Python dependencies
├── README.md                         # Main documentation
├── Core Scripts:
│   ├── send_metrics.py               # Main orchestration script
│   ├── get_metrics.py                # UISP data fetcher
│   ├── transform_metrics.py          # Data transformation
│   ├── insightfinder.py              # InsightFinder API client
│   └── cron.py                       # Automated scheduler
```

## Module Overview

### send_metrics.py

**Main orchestration script** - Coordinates the entire data pipeline

- Fetches devices from UISP
- Collects metrics with gap detection
- Transforms to InsightFinder format
- Sends data with retry logic
- Provides CLI with dry-run and verbose modes

### get_metrics.py

**UISP data collection** - Interfaces with UISP NMS API

- `get_devices()` - Fetch all devices
- `get_device_statistics()` - Fetch time-series metrics
- `extract_statistics()` - Parse and filter data with gap detection
- `is_active_60ghz_device()` - Filter active 60GHz devices

### transform_metrics.py

**Data transformation** - Converts UISP format to InsightFinder v2 format

- `sanitize_instance_name()` - Clean device names per InsightFinder rules
- `sanitize_metric_name()` - Clean metric names per InsightFinder rules
- `transform_uisp_to_insightfinder()` - Convert single device metrics to v2 format (dit structure)
- `transform_all_devices()` - Process all devices and return idm (Instance Data Map) structure

### insightfinder.py

**InsightFinder API client** - Handles all InsightFinder interactions

- `Config` - Configuration dataclass
- `InsightFinder` class:
  - `send_metric()` - Send metrics to v2 API with retry logic
  - `project_existed()` - Check project existence
  - `create_custom_project()` - Create new metric project
  - `_send_data()` - Internal method for v2 API requests
  - `_request()` - JSON POST request with retry (for v2 API)
  - `_request_form()` - Form-encoded POST request (for v1 API endpoints)
- `retry()` decorator - Exponential backoff for failed requests
- `chunks_by_size()` - Split data into byte-sized chunks

## Troubleshooting

### Missing Data / Data Gaps

If you notice missing data points (e.g., gaps between 16:45 and 16:55):

**1. Enable verbose mode to see gap detection:**

```bash
python send_metrics.py -v
```

**2. Look for gap warnings in the output:**

```
WARNING - Gap detected in AP-Building/signal: 2024-02-12 16:45:00 to 2024-02-12 16:55:00 (10.0 min, ~2 missing points)
WARNING - AP-Building/signal: Detected 1 gap(s) with ~2 missing data points
```

**3. Verbose mode shows human-readable timestamps:**

```json
{
  "timestamp": "1707753000000",
  "signal_avg[device]": "-45.2",
  "timestamp_readable": "2024-02-12 16:30:00"
}
```

*Note: `timestamp_readable` is only for debugging display, never sent to InsightFinder*

**4. Common solutions:**

```bash
# Fetch more historical data
python send_metrics.py --period 2h -v

# Use smaller sample interval
python send_metrics.py --sample-interval 1m -v

# Test with single device
python send_metrics.py -n 1 --dry-run -v
```

### No devices found

- Verify `UISP_URL` and `UISP_API_TOKEN` in `.env`
- Check that devices are active with 60GHz radio capability
- Use `python get_metrics.py --list-all` to view available devices

### Failed to send to InsightFinder

- Verify InsightFinder credentials in `.env`
- Check project exists or use `--create-project` flag
- Enable `--verbose` to see detailed error messages
- Check network connectivity to InsightFinder URL

### SSL Certificate Errors

- SSL verification is disabled for UISP (common for self-signed certs)
- Warnings are suppressed automatically

### Data format mismatch

- Ensure `INSIGHTFINDER_SAMPLING_INTERVAL` matches actual data frequency
- Verify device names don't contain disallowed characters (handled automatically)
- Use verbose mode to see data point counts at each stage
