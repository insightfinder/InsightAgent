# Ruckus Agent

Ruckus Agent is a Go-based data collection agent that fetches network performance metrics from a Ruckus SmartZone controller and sends them to InsightFinder for analysis and monitoring.

## Features

- **Concurrent Bulk Collection**: Fetches all AP and client data via paginated bulk queries with configurable concurrency
- **Client Enrichment**: Enriches per-AP metrics with RSSI, SNR, and TX statistics derived from individual client data
- **5GHz-only Critical Metrics**: Computes corroboration KPIs and critical alert indicators exclusively for 5GHz clients
- **Metric Filtering**: Per-metric enable/disable flags to control exactly what is sent to InsightFinder
- **Zone Mapping**: Optional JSON-based zone name remapping
- **Streaming Processing**: Processes APs in configurable chunks to bound memory usage

## Architecture

```
ruckus-agent/
├── configs/          # Configuration types and YAML loading
├── insightfinder/    # InsightFinder API client
├── pkg/models/       # Data models, metric conversion, utilities
│   ├── models.go     # APDetail, ClientInfo, MetricData, ToMetricData
│   └── utils.go      # Device name cleaning, zone mapping, POE parsing
├── ruckus/           # Ruckus SmartZone API client
│   ├── ruckus.go     # Authentication and HTTP client
│   ├── streaming.go  # Bulk AP pagination and streaming
│   ├── client_data.go # Client enrichment, 5GHz KPIs, alert indicators
│   ├── get_bulk_ap_data.go
│   └── type.go       # Request/response types
├── worker/           # Collection orchestration
│   ├── worker.go     # Lifecycle, scheduling, streaming loop
│   └── v1_send_data.go
└── main.go           # Entry point
```

## Configuration

Edit `configs/config.yaml`:

```yaml
agent:
  log_level: info        # debug | info | warn | error
  data_format: JSON
  timezone: UTC
  filters_include: ""    # Comma-separated AP name substrings to include
  filters_exclude: ""    # Comma-separated AP name substrings to exclude

ruckus:
  controller_host: 192.168.1.100
  controller_port: 8443
  username: your_ruckus_username
  password: your_ruckus_password
  api_version: v11_1     # v10_0 for SZ 5.x, v11_0/v11_1 for SZ 6.x
  verify_ssl: false
  max_concurrent_requests: 20
  send_component_name_as_AP: true

insightfinder:
  server_url: https://app.insightfinder.com
  username: your_if_username
  license_key: your_license_key_here
  project_name: RuckusWiFiMonitoring
  system_name: RuckusController
  project_type: Metric
  cloud_type: OnPremise
  instance_type: OnPremise
  is_container: false
  sampling_interval: 300   # seconds; 300 = 5-minute window

threshold:
  # Minimum number of 5GHz clients required before computing 5GHz KPIs
  # and critical alert indicators for an AP. APs below this count are skipped.
  min_clients_rssi_threshold: 10
  min_clients_snr_threshold: 10

metric_filter:
  # Set true to stream a metric to InsightFinder, false to suppress it.
  num_clients_total: false
  num_clients_24g: false
  num_clients_5g: false
  num_clients_6g: false

  airtime_24g: false
  airtime_5g: false
  airtime_6g: false
  airtime_24g_clients_over_35: true
  airtime_5g_clients_over_35: true
  airtime_6g_clients_over_35: true

  rssi_avg: false
  snr_avg: false
  clients_rssi_below_74: false
  clients_rssi_below_78: false
  clients_rssi_below_80: false
  clients_snr_below_15: false
  clients_snr_below_18: false
  clients_snr_below_20: false

  ethernet_status_mbps: true
```

## Installation

```bash
go mod download
go build -o ruckus-agent
```

## Running

```bash
./ruckus-agent
```

## Metrics Collected

### Standard AP Metrics (filter-gated)

These are enabled/disabled individually via `metric_filter` in `config.yaml`:

| Metric | Description |
|--------|-------------|
| `Num Clients Total` | Total associated clients |
| `Num Clients 24G` | Clients on 2.4GHz |
| `Num Clients 5G` | Clients on 5GHz |
| `Num Clients 6G` | Clients on 6GHz |
| `Airtime 24G Percent` | 2.4GHz channel utilization % |
| `Airtime 5G Percent` | 5GHz channel utilization % |
| `Airtime 6G Percent` | 6GHz channel utilization % |
| `Airtime 24G Clients > 35` | 2.4GHz airtime % (only if >35 clients, else 0) |
| `Airtime 5G Clients > 35` | 5GHz airtime % (only if >35 clients, else 0) |
| `Airtime 6G Clients > 35` | 6GHz airtime % (only if >35 clients, else 0) |
| `RSSI Avg` | Average RSSI across all clients (positive dBm) |
| `SNR Avg` | Average SNR across all clients (dB) |
| `% Clients RSSI < -74 dBm` | % clients in orange signal zone |
| `% Clients RSSI < -78 dBm` | % clients in red signal zone |
| `% Clients RSSI < -80 dBm` | % clients below red signal zone |
| `% Clients SNR < 15 dBm` | % clients below SNR 15 dB |
| `% Clients SNR < 18 dBm` | % clients below SNR 18 dB |
| `% Clients SNR < 20 dBm` | % clients below SNR 20 dB |
| `Ethernet Status Mbps` | WAN/uplink port speed parsed from POE port status |

### 5GHz Corroboration KPIs

Always sent when the AP has ≥ `min_clients_rssi_threshold` 5GHz clients. Computed as **p50 (median) across all 5GHz clients** for the current collection window.

5GHz clients are identified by `radioType` starting with `"a/"` (e.g. `a/n/ac`, `a/n/ac/ax`, `a/n`).

| Metric | Description |
|--------|-------------|
| `Median SNR 5GHz` | p50 SNR across 5GHz clients (dB) |
| `TX Retry Rate 5GHz` | p50 TX retry rate across 5GHz clients: `txDropDataFrames / txFrames × 100` (%) |

### Critical Alert Indicators (5GHz only)

Binary `1`/`0` metrics. Each fires independently when its specific pair of conditions is simultaneously true. Requires ≥ `min_clients_rssi_threshold` 5GHz clients per AP.

The RSSI condition shared by all critical indicators: **≥ 35% of 5GHz clients have RSSI < −78 dBm**.

| Metric sent to InsightFinder | Paired KPI condition |
|------------------------------|----------------------|
| `≥ 35% of clients RSSI < -78 dBm AND SNR/SINR < 18 dB` | Median SNR 5GHz < 18 dB |
| `≥ 35% of clients RSSI < -78 dBm AND TX Retry Rate > 18%` | Median TX Retry Rate 5GHz > 18% |
| `≥ 35% of clients RSSI < -78 dBm AND Airtime Utilization > 85%` | Airtime 5GHz > 85% |
| `≥ 35% of clients RSSI < -78 dBm AND Median MCS < 3` | Median TX MCS Rate 5GHz < 26,000 kbps (≈ MCS 3) |

**MCS threshold note**: The Ruckus API reports `medianTxMCSRate` in kbps. Based on 802.11n 20 MHz 1SS rates, MCS 3 = 26,000 kbps and MCS 7 = 65,000 kbps. The indicator uses `< 26,000 kbps` as the critical threshold.

## Troubleshooting

### No 5GHz KPI or Critical Indicator metrics appearing
- Check that the AP has ≥ `min_clients_rssi_threshold` 5GHz clients (`radioType` starting with `a/`)
- Enable `debug` log level to see per-AP client counts
- Verify client data is being fetched (look for "Client data collection complete" in logs)

### Standard metrics not appearing
- Confirm the relevant flag is `true` in `metric_filter` section of `config.yaml`

### Authentication failures
- Verify `controller_host`, `username`, and `password`
- Set `verify_ssl: false` for controllers with self-signed certificates
- Check `api_version` matches your SmartZone firmware:
  - SmartZone 5.x → `v10_0`
  - SmartZone 6.x → `v11_0` or `v11_1`

### High memory usage
- Reduce `max_concurrent_requests` to lower peak concurrency
- The worker streams APs in chunks; chunk size is set internally to 1000 APs

## Development

### Adding New Metrics

1. Add field to `APDetail` in `pkg/models/models.go`
2. Populate it in `ruckus/client_data.go:EnrichAPDataWithClientMetrics()` or `enrich5GHzMetrics()`
3. Send it in `pkg/models/models.go:ToMetricData()`
4. If filter-gated, add a flag to `MetricFilterConfig` in `configs/type.go` and implement the interface method

## License

Copyright InsightFinder Inc.
