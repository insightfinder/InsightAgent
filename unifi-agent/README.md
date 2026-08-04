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

# Optional: Device Inventory (Asset Registry) enrichment - leave both blank to disable.
# See "Device Inventory Enrichment" below.
JIRAASSET_BASE="http://your-accessparks-host"
JIRAASSET_API_KEY="your-accessparks-api-key"
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

Per AP instance, per supported band (5GHz only - see `SUPPORTED_BANDS` in `get_metrics.py`):

| Metric | Description |
|--------|-------------|
| `Channel Utilization (5GHz)` | Total airtime utilization % |
| `Clients (5GHz)` | Number of associated 5 GHz clients |
| `RSSI Average (5GHz)` | Average client RSSI (absolute dBm) |
| `SNR Average (5GHz)` | Average client SNR (dB) |
| `% Clients RSSI < -74/-78/-80 dBm (5GHz)` | % of clients below each RSSI threshold |
| `% Clients SNR < 15/18/20 dB (5GHz)` | % of clients below each SNR threshold |

Plus any rules defined in `DERIVED_METRICS_SCRIPT` (see `derived_metrics.py`).

---

## Device Inventory Enrichment

If `JIRAASSET_BASE` and `JIRAASSET_API_KEY` are set in `.env`, each AP is looked up in the internal Device Inventory (Asset Registry) API - by MAC, then serial number, then own name (first match wins) - and the result is cached in `aplookup.json` (matched) / `aplookupnotfound.json` (not found). Same API and lookup convention used by the baicells/positron/mimosa/netexperience/tarana-gnmic agents. If the two settings are left blank, enrichment is skipped entirely and no AP is ever matched.

The cache is refreshed two ways:
- **Immediately** for any AP seen for the first time (not yet in either cache file) - it doesn't wait for the schedule below.
- **Once daily**, in the 00:00–00:20 UTC window, `ap_inventory_lookup.py` re-runs against every AP - revalidating existing matches and retrying previous misses.

Values sent to InsightFinder, in priority order:

- **Instance name** (`in`): Inventory MAC (`MAC {mac}`) > Inventory serial (`SERIAL {serial}`) > Inventory object key (`JIRAKEY {object_key}`) > the AP's own name (cleaned - `_`/`:` become `-`). If none of these are available, the AP is **dropped** (not sent to InsightFinder) rather than sent under any other identifier. An Inventory miss alone does not drop the AP - it streams under its own name until Inventory resolves it. Values are never upper/lower-cased.
- **Instance display name** (`idn`): always the AP's own name as reported, raw/uncleaned - never falls back to the Inventory's name field.
- **Component name** (`cn`): Inventory's `manufacturer-device_class` only (from the matched record's `model`). Omitted if not in Inventory - no default.
- **Zone** (`z`): Inventory's `meta.subvenue` only. Omitted if not in Inventory - no default.
- **IP address** (`i`): Inventory's `ip_address` > the AP's own reported IP. Omitted if both are empty.

`aplookup.json`/`aplookupnotfound.json` are runtime caches regenerated as APs are seen (gitignored) - delete them to force a full re-lookup.

**Safety guarantees:**
- A brand-new AP is never sent under a bare/unenriched identity just because the cache doesn't have it yet - it's looked up immediately, and only sent (under its own name) once that lookup actually completes (found or confirmed not-found).
- If the lookup itself errors (Inventory API down), the AP is skipped entirely for that cycle and retried next time - it does not fall back to sending raw.
- Inventory API errors never evict an existing good match from the cache - only a confirmed miss updates `aplookupnotfound.json`.

---

## Key Files

| File | Purpose |
|------|---------|
| `get_metrics.py` | Fetch AP radio stats and print to terminal |
| `send_metrics.py` | Collect metrics and send to InsightFinder in a loop |
| `ap_inventory_lookup.py` | Device Inventory (Asset Registry) lookup - batch script and the `resolve_ap()` helper `send_metrics.py` uses for first-seen APs |
| `insightfinder.py` | InsightFinder API client (metric + log ingestion) |
| `example.env` | Config template — copy to `.env` |

---

## How It Works

1. **List sites** — `GET /v1/sites` → `hostId` + `siteSlug` for each site
2. **Fetch device stats** — `GET /v1/connector/consoles/{hostId}/proxy/network/api/s/{siteSlug}/stat/device`
3. Extract `cu_total`, `cu_self_rx`, `cu_self_tx` from each radio in `radio_table_stats`
4. Send as metric data points to InsightFinder's v2 API

> The official integration-v1 `statistics/latest` endpoint does not expose channel utilization. The legacy `/proxy/network/api/` path (used by the UniFi web UI) is required.
