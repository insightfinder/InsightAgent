# unifi-agent

Collects channel utilization metrics from UniFi access points across all managed sites and forwards them to InsightFinder.

API docs:
- [Site Manager API v1.0.0](https://developer.ui.com/site-manager/v1.0.0/gettingstarted)
- [Network API v10.1.84](https://developer.ui.com/network/v10.1.84/gettingstarted)

---

## Setup

```bash
cp example.env .env
# fill in credentials (see Configuration section below)
pip install requests
```

The UniFi API key must belong to the **console owner** — a read-only/invited-user key returns `403` on Cloud Connector paths.

Generate one at: **unifi.ui.com → Settings → API Keys**

---

## Configuration

Edit `.env` with your credentials:

```env
UNIFI_API_KEY="your-api-key"

INSIGHTFINDER_URL="https://stg.insightfinder.com"
INSIGHTFINDER_USER_NAME="your-username"
INSIGHTFINDER_LICENSE_KEY="your-license-key"
INSIGHTFINDER_PROJECT_NAME="unifi-metrics"
INSIGHTFINDER_SYSTEM_NAME="your-system-name"   # optional
INSIGHTFINDER_SAMPLING_INTERVAL="5"            # minutes between collections
```

---

## Usage

### Print metrics to terminal

```bash
python3 get_metrics.py
```

### Send metrics to InsightFinder (continuous loop)

```bash
python3 send_metrics.py
python3 send_metrics.py --verbose   # print full payload before each send
```

`send_metrics.py` runs indefinitely, sleeping `INSIGHTFINDER_SAMPLING_INTERVAL` minutes between collections.

---

## Output

`get_metrics.py` prints channel utilization per radio per AP, grouped by site:

```
site            ap_name   band    ChUtil_Busy  ChUtil_Rx  ChUtil_Tx  status
--------------  --------  ------  -----------  ---------  ---------  ------
Bamboo MHC      U6+       2.4GHz  12           4          8          online
Bamboo MHC      U6+       5GHz    7            2          5          online
```

- **ChUtil_Busy** — total channel busy % (Rx + Tx + interference)
- **ChUtil_Rx** — time AP spent receiving
- **ChUtil_Tx** — time AP spent transmitting

---

## Metrics sent to InsightFinder

Per AP instance, per supported band (2.4GHz / 5GHz):

| Metric | Description |
|--------|-------------|
| `ChUtil_Busy_2.4GHz` | Channel busy % on 2.4 GHz |
| `ChUtil_Rx_2.4GHz` | Receive utilization % on 2.4 GHz |
| `ChUtil_Tx_2.4GHz` | Transmit utilization % on 2.4 GHz |
| `ChUtil_Busy_5GHz` | Channel busy % on 5 GHz |
| `ChUtil_Rx_5GHz` | Receive utilization % on 5 GHz |
| `ChUtil_Tx_5GHz` | Transmit utilization % on 5 GHz |

**Instance names** use the AP's IP address if available, otherwise the AP name (sanitized: spaces/commas/underscores/`@#:` → `-`). Component names are set to the sanitized site name.

---

## Key Files

| File | Purpose |
|------|---------|
| `get_metrics.py` | Fetch AP radio stats and print to terminal |
| `send_metrics.py` | Collect metrics and send to InsightFinder in a loop |
| `insightfinder.py` | InsightFinder API client (metric + log ingestion) |
| `example.env` | Config template — copy to `.env` |

---

## How It Works

1. **List sites** — `GET /v1/sites` → `hostId` + `siteSlug` for each site
2. **Fetch device stats** — `GET /v1/connector/consoles/{hostId}/proxy/network/api/s/{siteSlug}/stat/device`
3. Extract `cu_total`, `cu_self_rx`, `cu_self_tx` from each radio in `radio_table_stats`
4. Send as metric data points to InsightFinder's v2 API

> The official integration-v1 `statistics/latest` endpoint does not expose channel utilization. The legacy `/proxy/network/api/` path (used by the UniFi web UI) is required.
