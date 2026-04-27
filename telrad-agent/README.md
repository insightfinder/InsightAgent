# accessparks-telrad-agent

Agent for querying signal metrics from the AccessParks Telrad BreezeVIEW via its REST NBI API.

## Setup

Copy `.env` and fill in your credentials:

```
ACCESSPARKS_TELRAD_URL=http://<host>:<port>
ACCESSPARKS_TELRAD_USERNAME=<username>
ACCESSPARKS_TELRAD_PASSWORD=<password>
```

---

## Device Summary

### Device types in the system

BreezeVIEW manages eNB LTE base stations that expose eNB-side uplink signal metrics in dBm via REST.

### Signal metrics via REST NBI

Available for all managed eNBs via a single HTTP GET. The agent collects per-UE:

| Metric   | Unit | Description                                    |
|----------|------|------------------------------------------------|
| `UlRSSI` | dBm  | Uplink received signal strength (eNB-measured) |
| `UlCINR` | dB   | Uplink carrier-to-interference ratio           |

Unreachable eNBs return an RPC fault — no metrics available.

### Key REST gotchas: device enumeration

`GET /api/running/devices/device?shallow` **hangs** and only returns the first 2 devices. Always use semicolon-separated fields (comma syntax returns empty elements):

```
GET /api/running/devices/device?select=name;address
```

This returns all device IDs with their IPs quickly.

**Deduplicate by IP** — some eNBs may share the same IP (registered twice in NCS). Querying both returns identical metrics. `get_metrics.py` deduplicates by IP automatically.

---

## Python Script — Fetch All Devices' Signal Metrics

`get_metrics.py` queries all eNBs via the REST NBI and reports their signal metrics.

### Run

```bash
# Human-readable summary (default)
python3 get_metrics.py

# Summary to stdout + JSON to file
python3 get_metrics.py --output metrics.json

# Single device only
python3 get_metrics.py --device 20

# JSON to stdout (no summary)
python3 get_metrics.py --json-only

# JSON to file (no summary)
python3 get_metrics.py --json-only --output metrics.json

# Longer timeout for slow networks
python3 get_metrics.py --timeout 30
```

### Sample output

```
[device 10]  UNREACHABLE — HTTP 400: Bad Request
[device 20]  UEs: 61
    TEID 20  RNTI 132  Cell 0  UlRSSI -74 dBm  UlCINR 20 dB
    TEID 42  RNTI 155  Cell 1  UlRSSI -81 dBm  UlCINR 14 dB
    ... and 59 more UEs
[device 55]  UEs: 3
```

Errors from unreachable eNBs are expected and included in the JSON output with `"status": "error"`.

### JSON output shape

```json
{
  "timestamp": "2026-04-24T13:00:00Z",
  "devices": [
    {
      "device_id": "20",
      "status": "ok",
      "ues": [
        {
          "teid": "20",
          "rnti": 132,
          "cell_id": 0,
          "ul_rssi_dbm": -74,
          "ul_cinr_db": 20
        }
      ]
    },
    {
      "device_id": "10",
      "status": "error",
      "error": "HTTP 400: Bad Request"
    }
  ]
}
```
