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
UISP_MAX_WORKERS="10"  # concurrent requests when fetching device detail
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

Metrics are sent to InsightFinder v2 API with the following structure. `idn`/`cn`/`i`/`z` are packed into a single `im` JSON string, not sent as flat top-level keys - matches baicells-agent/tarana-gnmic-agent's validated wire format:

```json
{
  "idm": {
    "MAC 24-5A-4C-F6-82-B0": {
      "in": "MAC 24-5A-4C-F6-82-B0",
      "im": "{\"idn\": \"device-name\", \"cn\": \"Ubiquiti-airFiber\", \"i\": \"192.168.1.1\", \"z\": \"East Toho\"}",
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

## Device Inventory Enrichment

If `JIRAASSET_BASE` and `JIRAASSET_API_KEY` are set in `.env`, each device is looked up in the internal Device Inventory (Asset Registry) API - by MAC, then serial number, then own name (first match wins) - and the result is cached in `devicelookup.json` (matched) / `devicelookupnotfound.json` (not found). Same API and lookup convention used by the baicells/positron/unifi/mimosa/netexperience/tarana-gnmic agents. If the two settings are left blank, enrichment is skipped entirely and devices are sent under their own name as before.

The cache is refreshed two ways:
- **Immediately** for any device seen for the first time - it doesn't wait for the schedule below.
- **Once daily**, in the 00:00-00:20 UTC window, `device_inventory_lookup.py` re-runs against every device - revalidating existing matches and retrying previous misses.

Values sent to InsightFinder, in priority order:

- **Instance name** (`in`): Inventory MAC (`MAC {mac}`) > Inventory serial (`SERIAL {serial}`) > Inventory object key (`JIRAKEY {object_key}`) > the device's own name (cleaned - `_`/`:` become `-`). If none of these are available, the device is **dropped** (not sent to InsightFinder) rather than sent under any other identifier. An Inventory miss alone does not drop the device - it streams under its own name until Inventory resolves it. If the Inventory API errors on a lookup (not a confirmed miss), the device is skipped entirely for that run and retried next time, rather than sent under a bare/unenriched identity.
- **Instance display name** (`idn`): always the device's own name as reported, raw/uncleaned - never falls back to the Inventory's name field.
- **Component name** (`cn`): Inventory's `manufacturer-device_class` only. Omitted if not in Inventory - no default.
- **Zone** (`z`): Inventory's `meta.subvenue` only. Omitted if not in Inventory - no default.
- **IP address** (`i`): Inventory's `ip_address` > the device's own reported IP. Omitted if both are empty.

`devicelookup.json`/`devicelookupnotfound.json` are runtime caches regenerated as devices are seen (gitignored) - delete them to force a full re-lookup.

> **Note:** enabling this changes existing devices' instance identity from their sanitized own name to `MAC {mac}` (once matched) - this breaks continuity with any existing InsightFinder history/alerts keyed on the old instance names. Confirm this is intended before enabling on a project with existing data.

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
| `UISP_MAX_WORKERS` | Concurrent requests fetching device detail | `10` |
| `JIRAASSET_BASE` | Device Inventory API base URL (optional) | `http://54.234.90.98` |
| `JIRAASSET_API_KEY` | Device Inventory API key (optional) | - |

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

- Increase `UISP_MAX_WORKERS` in `.env` (default: 3)
- Concurrent requests speed up device detail fetching significantly
- `device_inventory_lookup.py`'s Inventory lookups are sequential, not concurrent - a full run across all devices can take several minutes

### SSL Certificate Errors

- SSL verification is disabled for UISP (self-signed certs are common)
- Warnings are suppressed automatically

## Project Files

- `send_metrics.py` - Main script (fetch → transform → send)
- `get_metrics.py` - UISP API interaction
- `transform_metrics.py` - Data transformation to v2 format
- `device_inventory_lookup.py` - Device Inventory (Asset Registry) lookup - batch script and the `resolve_device()` helper `send_metrics.py` uses for first-seen devices
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

- Instance identity follows the Device Inventory priority above; see that section for naming/cleanup rules
- Signal values converted to absolute (positive) values
- Only active devices are processed
- Per-station metrics use first connected station only
