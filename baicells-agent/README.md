# BaiCells Agent

Python client for interacting with the BaiCells RESTful API to get signal metrics of CPE devices.

## Overview

This project provides:

- **`baicells_client.py`**: Python library for BaiCells RESTful API
- **`get_metrics.py`**: CLI tool to poll and display CPE signal metrics
- **`send_metrics.py`**: CLI tool to poll CPE metrics and send to InsightFinder
- **`insightfinder.py`**: InsightFinder client library for metric streaming
- **`cpe-device-sn.txt`**: Static CPE devices serial number copying from <https://cloudcore.baicells.com>

**Note: Currently, the CPE device serial number can not be get by API on runtime. The only way is to use the serial number in cpe-device-sn.txt**

## Features

- **Device Groups**: Fetch all device groups with hierarchical structure
- **CPE Signal Metrics**: Retrieve signal quality metrics (RSRP, RSRQ, SINR, CINR) from CPE devices
- **InsightFinder Integration**: Stream metrics to InsightFinder

## Setup

1. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

   Or manually:

   ```bash
   pip install python-dotenv requests
   ```

2. **Configure credentials:**

   Copy `example.env` to `.env` and fill in your credentials:

   ```bash
   cp example.env .env
   ```

   Then edit `.env` with your values:

   ```env
   BAICELLS_URL=https://cloudcore.baicells.com:7085
   BAICELLS_USERNAME=your_username
   BAICELLS_PASSWORD=your_password

   # InsightFinder Configuration (only needed for send_metrics.py)
   INSIGHTFINDER_BASE_URL="https://stg.insightfinder.com"
   INSIGHTFINDER_USER_NAME="your_if_username"
   INSIGHTFINDER_LICENSE_KEY="your_license_key"
   INSIGHTFINDER_PROJECT_NAME="baicells-metrics"
   INSIGHTFINDER_SYSTEM_NAME=""
   INSIGHTFINDER_SAMPLING_INTERVAL="15"  # in minutes
   ```

## Usage

All scripts support a `-v` or `--verbose` flag to enable detailed debug logging for troubleshooting API issues or understanding the data flow.

### 1. Poll CPE Signal Metrics (`get_metrics.py`)

Note: The API call has rate limit of 20 times/1min

Get CPE signal metrics (RSRP, RSRQ, SINR, CINR) at regular intervals without sending to InsightFinder:

```bash
# Poll a specific CPE device every 1 minute for 10 iterations
python3 get_metrics.py 1203000141216BB3570 --interval 60 --iterations 10

# Poll all online CPE devices every 30 seconds
python3 get_metrics.py --interval 30

# Poll first 5 online CPE devices every minute
python3 get_metrics.py --devices 5 --interval 60

# Poll devices from a file
python3 get_metrics.py --file my-cpes.txt --interval 60

# Enable verbose logging
python3 get_metrics.py 1203000141216BB3570 -v
```

**Command-line Options:**

- `serial_number`: (Optional) CPE serial number to monitor
- `-f, --file FILE`: Read CPE serial numbers from a file (one per line)
- `-i, --interval SECONDS`: Polling interval in seconds (default: 60)
- `-n, --iterations COUNT`: Maximum number of polling iterations (default: infinite)
- `-d, --devices COUNT`: Maximum number of CPE devices to monitor (default: all)
- `--url`: Override BaiCells API base URL from .env
- `--username`: Override API username from .env
- `--password`: Override API password from .env
- `-v, --verbose`: Enable verbose debug logging

**Device Selection Priority:**

1. Explicit `serial_number` argument
2. `--file` argument
3. Default `cpe-device-sn.txt` file
4. Auto-discover all online CPE devices

### 2. Send Metrics to InsightFinder (`send_metrics.py`)

Poll CPE signal metrics and stream them continuously to InsightFinder:

```bash
# Poll devices from cpe-device-sn.txt (default) with configuration in .env
python3 send_metrics.py

# Poll a specific CPE every 300 seconds
python3 send_metrics.py 1203000141216BB3570 --interval 300

# Poll devices from a custom file for 10 iterations
python3 send_metrics.py --file devices.txt --iterations 10

# Enable logging to file with rotation
python3 send_metrics.py --log-file output.log --log-max-bytes 10485760 --log-backup-count 5
```

**Command-line Options:**

All device-selection flags from `get_metrics.py`, plus:

- `--if-url`: InsightFinder URL (overrides .env)
- `--if-user`: InsightFinder username (overrides .env)
- `--if-key`: InsightFinder license key (overrides .env)
- `--if-project`: InsightFinder project name (overrides .env)
- `--log-file FILE`: Write log messages to file instead of stdout
- `--log-max-bytes BYTES`: Max log file size before rotation (default: 10 MiB)
- `--log-backup-count N`: Number of rotated log files to keep (default: 5)
**Metrics Sent per Device:**

- **LTE**: `rsrp0`, `rsrp1`, `sinr`, `cinr0`, `cinr1`
- **5G NR** (when available): `nr_rsrp`, `nr_rsrq`, `nr_sinr`, `nr_cinr`

**Rate Limiting:**

Devices are processed in batches of 20 with 60-second intervals between batches to respect API rate limits.

### 3. Using the Client Library (`baicells_client.py`)

The `BaiCellsClient` class can be used programmatically in your own Python scripts:

```python
from baicells_client import BaiCellsClient

# Initialize client (reads credentials from .env automatically)
client = BaiCellsClient()

# Or pass credentials explicitly
client = BaiCellsClient(
    base_url="https://cloudcore.baicells.com:7085",
    username="your_username",
    password="your_password"
)

# Get all device groups
groups = client.get_all_groups()
print(f"Found {len(groups)} groups")

# Get devices for a specific group (by group ID)
devices = client.get_devices_by_group(group_id=2247)
print(f"Found {len(devices)} devices in group")

# Get all CPE devices across all groups
result = client.get_all_cpes()
print(f"Total CPE devices: {result['summary']['total_devices']}")
print(f"Online CPE devices: {result['summary']['online_devices']}")

# Get all devices (CPE and eNB/gNB) across all groups
result = client.get_all_devices()
print(f"Total devices: {result['summary']['total_devices']}")

# Get status of a specific eNB device
status = client.get_enb_status('1203000141216BB3570')
print(f"Cell State: {status.get('cellState')}")

# Get CPE connection status
cpe_status = client.get_cpe_status('1203000141216BB3570')
print(f"Connection: {cpe_status.get('connectionStatus')}")

# Get detailed CPE signal quality metrics
cpe_info = client.get_cpe_info('1203000141216BB3570')
print(f"RSRP: {cpe_info.get('rsrp0')} dBm")
print(f"SINR: {cpe_info.get('cpeSinr')} dB")

# For 5G devices
if cpe_info.get('nrRsrp'):
    print(f"5G RSRP: {cpe_info.get('nrRsrp')} dBm")
    print(f"5G SINR: {cpe_info.get('nrSinr')} dB")
```

## API Reference

### BaiCellsClient Class

#### Constructor

```python
BaiCellsClient(base_url=None, username=None, password=None, timeout=10)
```

**Parameters:**

- `base_url`: BaiCells API base URL (defaults to `BAICELLS_URL` or `BAICELLS_BASE_URL` from .env)
- `username`: API username (defaults to `BAICELLS_USERNAME` from .env)
- `password`: API password (defaults to `BAICELLS_PASSWORD` from .env)
- `timeout`: Request timeout in seconds (default: 10)

#### Methods

##### `authenticate() -> str`

Authenticate and get access token. Automatically manages token expiry (tokens are valid for 30 minutes).

**Returns:** Access token string

---

##### `get_all_groups(search_text=None) -> list[dict]`

Get all device groups with hierarchical structure flattened.

**Parameters:**

- `search_text` (optional): Search filter for group names

**Returns:** List of group dictionaries with keys:

- `id`: Group ID (int for child groups, str for parent groups)
- `name`: Group name
- `description`: Group description
- `built_in`: Whether it's a system default group (1) or user-created (0)
- `parent_name`: Parent group name (None for top-level groups)

---

##### `get_devices_by_group(group_id, page_size=100, search_text=None) -> list[dict]`

Get all devices for a specific group (handles pagination automatically).

**Parameters:**

- `group_id`: Group ID (must be integer - use child group IDs only)
- `page_size`: Number of devices per page (default: 100)
- `search_text` (optional): Search filter

**Returns:** List of device dictionaries with fields including:

- `serial_number`: Device serial number
- `host_name`: Device name
- `connection_status`: "On" (online) or "Off" (offline)
- `group_name`: Full group path (e.g., "Parent/Child")
- `mac_address`, `software_version`, `product`, `longitude`, `latitude`, etc.

---

##### `get_cpes_by_group(group_id, page_size=100, search_text=None) -> list[dict]`

Get all CPE devices for a specific group. CPE devices are identified by validating against the CPE info endpoint.

**Parameters:**

- `group_id`: Group ID (must be integer)
- `page_size`: Number of devices per page (default: 100)
- `search_text` (optional): Search filter

**Returns:** List of validated CPE device dictionaries

---

##### `get_all_devices(page_size=100) -> dict`

Get all devices (CPE and eNB/gNB) from all groups.

**Parameters:**

- `page_size`: Number of devices per page for pagination (default: 100)

**Returns:** Dictionary containing:

- `groups`: List of all groups
- `devices_by_group`: Dictionary mapping group_id to list of devices
- `all_devices`: Flattened list of all devices
- `summary`: Statistics dictionary with:
  - `total_groups`: Total number of groups
  - `queryable_groups`: Number of child groups (with integer IDs)
  - `total_devices`: Total device count
  - `groups_with_devices`: Number of groups that contain devices
  - `online_devices`: Number of online devices

---

##### `get_all_cpes(page_size=100) -> dict`

Get all CPE devices from all groups. Similar to `get_all_devices()` but filters and validates only CPE devices.

**Parameters:**

- `page_size`: Number of devices per page for pagination (default: 100)

**Returns:** Dictionary with the same structure as `get_all_devices()`, but containing only validated CPE devices

---

##### `get_enb_status(serial_number) -> dict`

Get running status of a specific eNB device.

**Parameters:**

- `serial_number`: eNB device serial number

**Returns:** Device status dictionary with:

- `cellState`: Cell state (0: Not Activated, 1: Activated)
- `syncStatus`: Synchronization status (0: failed, 1: succeed)
- Other status fields...

---

##### `get_cpe_status(serial_number) -> dict`

Get CPE (Customer Premises Equipment) connection status.

**Parameters:**

- `serial_number`: CPE serial number

**Returns:** CPE status dictionary with:

- `connectionStatus`: "on" (online) or "off" (offline)
- `serialNumber`: CPE serial number

---

##### `get_cpe_info(serial_number) -> dict`

Get detailed CPE information including comprehensive signal quality metrics. This is the primary method for monitoring CPE radio performance.

**Parameters:**

- `serial_number`: CPE serial number

**Returns:** CPE info dictionary with extensive fields including:

**Signal Quality Metrics (LTE):**

- `rsrp0`, `rsrp1`: Reference Signal Received Power for antenna 0 and 1 (dBm)
- `cpeSinr`: Signal-to-Interference-plus-Noise Ratio (dB)
- `cinr0`, `cinr1`: Carrier to Interference plus Noise Ratio (dB)

**Signal Quality Metrics (5G NR):**

- `nrRsrp`: 5G Reference Signal Received Power (dBm)
- `nrRsrq`: 5G Reference Signal Received Quality (dB)
- `nrSinr`: 5G Signal-to-Interference-plus-Noise Ratio (dB)
- `nrCinr`: 5G Carrier to Interference plus Noise Ratio (dB)

**Network Information:**

- `bandwidth`, `nrBandwidth`: LTE/5G bandwidth (MHz)
- `pci`, `nrPci`: Physical Cell ID
- `cellIdentity`, `nrCellId`: Cell identity
- `mcc`, `mnc`: Mobile Country/Network Code
- `dlEarfcn`, `nrEarfcn`: Downlink frequency channel numbers

**Performance Metrics:**

- `txPower`: Transmit power (dBm)
- `dlCurrentDataRate`, `ulCurrentDataRate`: Current data rates (Mbps)
- `dlMcs`, `ulMcs`: Modulation and Coding Scheme
- `dlBler`: Downlink Block Error Rate

**Device Information:**

- `cpeName`: CPE device name
- `macaddress`: MAC address
- `ipaddress`: IP address
- `softwareVersion`: Software version
- `connectionStatus`: Connection status
- `onlineTime`, `offlineTime`: Connection timestamps

**Example:**

```python
client = BaiCellsClient()
cpe_info = client.get_cpe_info('CPE123456')

# Check signal quality
rsrp = cpe_info.get('rsrp0')
sinr = cpe_info.get('cpeSinr')
print(f"RSRP: {rsrp} dBm, SINR: {sinr} dB")

# For 5G devices
if cpe_info.get('nrRsrp'):
    print(f"5G RSRP: {cpe_info.get('nrRsrp')} dBm")
```

## CPE Device Files

### cpe-device-sn.txt

Default file containing CPE serial numbers (one per line) for monitoring. Used by both `get_metrics.py` and `send_metrics.py` when no specific device is specified.

Lines starting with `#` are treated as comments and ignored.

## Project Structure

```text
baicells-agent/
├── baicells_client.py     # BaiCells API client library
├── get_metrics.py         # CLI tool to poll CPE signal metrics
├── send_metrics.py        # CLI tool to send metrics to InsightFinder
├── insightfinder.py       # InsightFinder client library
├── cpe-device-sn.txt      # Default CPE serial numbers file
├── example.env            # Example environment configuration
├── requirements.txt       # Python dependencies
└── README.md              # This file
```

## Notes

- **Group IDs**: Parent group IDs are strings; child group IDs are integers. Only child groups (with integer IDs) can be queried for devices.
- **Token Expiry**: Tokens expire after 30 minutes. The client automatically refreshes tokens as needed.
- **Pagination**: The client automatically handles pagination when fetching devices.
- **Rate Limiting**: Both scripts use batching (20 devices per batch) with 60-second intervals between batches to respect API rate limits.
- **CPE Validation**: CPE devices are validated by testing against the CPE info endpoint to ensure only actual CPE devices are monitored (not eNB/gNB base stations).

## Troubleshooting

### ModuleNotFoundError: No module named 'dotenv'

Install dependencies:

```bash
pip install -r requirements.txt
```

### Authentication failed

- Verify credentials in `.env` file
- Check that the API URL is correct
- Ensure your user account has API access enabled in BaiCells OMC

### No CPE devices found

- Verify that CPE devices are online in the OMC web interface
- Check that devices are assigned to groups
- Ensure the serial numbers in `cpe-device-sn.txt` are correct
- Use the `--verbose` flag to see detailed device validation logs

### InsightFinder connection failed

- Verify InsightFinder credentials in `.env` file
- Check that the InsightFinder URL is accessible
- Ensure the project exists in InsightFinder (create it manually or use `create_project=True`)

## License

See the LICENSE file for details.
