# UISP to InsightFinder Integration

Agent for collecting metrics from UISP devices and sending them to InsightFinder.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```bash
# UISP Configuration
UISP_URL="https://your-uisp-instance.com"
UISP_API_TOKEN="your-api-token"

# InsightFinder Configuration
INSIGHTFINDER_BASE_URL="https://your-insightfinder-instance.com"
INSIGHTFINDER_USER_NAME="your-username"
INSIGHTFINDER_LICENSE_KEY="your-license-key"
INSIGHTFINDER_PROJECT_NAME="uisp-metrics"
INSIGHTFINDER_SYSTEM_NAME="uisp"

# Optional
INSIGHTFINDER_SAMPLING_INTERVAL="5"  # minutes
MAX_CONCURRENT_REQUESTS="10"  # concurrent API requests
```

### 3. Send Metrics

```bash
# Send all device metrics
python send_metrics.py

# Limit to N devices (useful for testing)
python send_metrics.py -n 5

# Verbose output with payload details
python send_metrics.py -v

# Test without sending (dry run)
python send_metrics.py --dry-run
```

## Supported Metrics

### airFiber (PTP/PTMP)
- `signal` - Link signal strength (dBm)
- `downlinkUtilization` - Downlink utilization (%)
- `uplinkUtilization` - Uplink utilization (%)
- `activeStationsCount` - Connected stations
- `downlinkCapacity`, `uplinkCapacity` - First station capacity
- `txMcs`, `rxMcs` - First station modulation

### airMax (WiFi AP)
- Same as airFiber

### OLT (Fiber Access Point)
- `activeStationsCount` - Connected ONUs

### ONU (Fiber Client)
- `signal` - Optical signal strength (dBm)
- `receivePower` - Receive power (dBm)
- `rxRate` - Receive bit rate (bps)
- `txRate` - Transmit bit rate (bps)

## Data Format

Metrics are sent to InsightFinder v2 API with the following structure:

```json
{
  "idm": {
    "device-name": {
      "in": "device-name",
      "i": "192.168.1.1",
      "dit": {
        "1707753000000": {
          "t": 1707753000000,
          "metricDataPointSet": [
            {"m": "signal", "v": 45.0},
            {"m": "downlinkUtilization", "v": 2.5}
          ]
        }
      }
    }
  }
}
```

## Configuration

| Parameter | Description | Example |
|-----------|-------------|---------|
| `UISP_URL` | UISP NMS base URL | `https://nms.example.com` |
| `UISP_API_TOKEN` | UISP API token | Token from UISP UI |
| `INSIGHTFINDER_BASE_URL` | InsightFinder URL | `https://app.insightfinder.com` |
| `INSIGHTFINDER_USER_NAME` | InsightFinder username | Your username |
| `INSIGHTFINDER_LICENSE_KEY` | License key | From Account Profile |
| `INSIGHTFINDER_PROJECT_NAME` | Project name | `uisp-metrics` |
| `INSIGHTFINDER_SYSTEM_NAME` | System identifier | `uisp` |
| `INSIGHTFINDER_SAMPLING_INTERVAL` | Sampling interval in minutes | `5` |
| `MAX_CONCURRENT_REQUESTS` | Concurrent API requests | `10` |

## Automation / Scheduling

### Using APScheduler (cron.py)

```bash
python cron.py
```

The scheduler runs `send_metrics.py` automatically at intervals specified in `.env`:

- Reads `INSIGHTFINDER_SAMPLING_INTERVAL` from `.env`
- Runs at that interval (e.g., every 5 minutes)
- Cross-platform (Linux, macOS, Windows)
- Press Ctrl+C to stop

## Troubleshooting

### No metrics appearing in InsightFinder

1. **Check credentials** - Verify `.env` file has correct tokens
2. **Check project exists** - Project will be auto-created if missing
3. **Enable verbose mode** - See payload being sent:
   ```bash
   python send_metrics.py -n 1 -v
   ```
4. **Check device status** - Only active devices are processed
5. **Check metrics are extracted** - Look for device type in logs

### Slow performance

- Increase `MAX_CONCURRENT_REQUESTS` in `.env` (default: 5)
- Concurrent requests speed up device detail fetching significantly

### SSL Certificate Errors

- SSL verification is disabled for UISP (self-signed certs are common)
- Warnings are suppressed automatically

## Project Files

- `send_metrics.py` - Main script (fetch → transform → send)
- `get_metrics_new.py` - UISP API interaction
- `transform_metrics.py` - Data transformation to v2 format
- `insightfinder.py` - InsightFinder API client
- `cron.py` - Automated scheduler
- `requirements.txt` - Python dependencies
- `.env` - Configuration (create this file)

## CLI Options

### send_metrics.py

| Option | Description |
|--------|-------------|
| `-n, --limit N` | Limit to first N devices |
| `--dry-run` | Preview without sending |
| `-v, --verbose` | Show detailed payload |
| `--no-create-project` | Don't auto-create project |

## Notes

- Device names are sanitized (underscores → hyphens, special chars removed)
- Signal values converted to absolute (positive) values
- Only active devices are processed
- Per-station metrics use first connected station only
- IP address extracted from device and included in data
