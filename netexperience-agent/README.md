# NetExperience Agent

NetExperience Agent is a Go-based data collection agent that fetches network performance metrics from the NetExperience API and sends them to InsightFinder for analysis and monitoring.

## Features

- **Robust Authentication**: Automatic token management with refresh and retry mechanisms
- **Rate Limiting**: Configurable rate limiting (default: 180 requests per 10 seconds)
- **Smart Caching**: Daily cache refresh for customers and equipment data to minimize API calls
- **Concurrent Processing**: Processes multiple customers and equipment in batches
- **Comprehensive Metrics**: Collects AP metrics including:
  - Client counts (5GHz, 2.4GHz, total)
  - Channel utilization per radio
  - RSSI statistics and client distribution across signal strength levels
  - 5GHz corroboration KPIs: SNR and TX retry rate
  - **Critical RF indicators**: three separate binary metrics, each pairing the RSSI condition with a different 5GHz KPI threshold

## Architecture

```
netexperience-agent/
├── configs/          # Configuration management
├── insightfinder/    # InsightFinder API client
├── netexperience/    # NetExperience API client
│   ├── netexperience.go  # Authentication and token management
│   ├── util.go           # API client methods
│   ├── cache.go          # Cache management
│   └── type.go           # Type definitions
├── pkg/models/       # Data models
├── worker/           # Main processing logic
│   ├── worker.go     # Worker lifecycle
│   └── process.go    # Metric processing and sending
└── main.go           # Entry point
```

## Configuration

Edit `configs/config.yaml` to configure the agent:

```yaml
netexperience:
  base_url: https://cmap-portal-svc.prod1.netexperience.com
  user_id: your-email@example.com
  password: your-password
  service_provider_id: 58
  
  # Token management
  token_refresh_interval: 82800  # 23 hours
  token_retry_attempts: 3
  token_retry_delay: 5  # seconds
  
  # Rate limiting
  rate_limit_requests: 180
  rate_limit_period: 10  # seconds
  
  # Data collection
  max_concurrent_requests: 5
  equipment_batch_size: 5
  
  # Cache settings
  customer_cache_refresh_hours: 24
  equipment_cache_refresh_hours: 24
  equipment_ip_cache_refresh_hours: 24
  
  # Thresholds — metrics are omitted entirely when AP client count is below these values
  min_clients_rssi_threshold: 10
  min_clients_snr_threshold: 10

  # Device Inventory API (MAC -> serial/venue/component lookup)
  device_inventory_api_key: your-api-key
  device_inventory_base_url: http://54.234.90.98
  device_inventory_timeout_sec: 5
  device_inventory_max_retry: 2

insightfinder:
  server_url: https://stg.insightfinder.com
  username: your-username
  license_key: your-license-key
  metrics_project_name: NetExperience-Metrics
  sampling_interval: 60
```

**Note:** The agent will automatically create the InsightFinder project if it doesn't exist.

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   cd netexperience-agent
   go mod download
   ```
3. Configure `configs/config.yaml`
4. Build:
   ```bash
   go build -o netexperience-agent
   ```

## Running

```bash
./netexperience-agent
```

## How It Works

### Authentication Flow

1. **Initial Login**: Agent logs in using username/password to get an access token
2. **Token Refresh**: Token is automatically refreshed every 23 hours
3. **Retry Mechanism**: Failed requests trigger token refresh or re-login
4. **Fallback**: If refresh fails, agent re-authenticates from scratch

### Data Collection Flow

1. **Cache Management**:
   - Fetches customer list once per day
   - Fetches equipment list for each customer once per day
   - Reuses cached data between sampling intervals

2. **Metric Collection** (every sampling interval):
   - Calculates time range (last 1 minute)
   - Processes each customer's equipment in batches
   - Fetches service metrics (ApNode and Client data)
   - Aggregates metrics per equipment

3. **Metric Processing**:
   - Combines ApNode metrics (latest) with Client metrics
   - Calculates RSSI statistics and percentages
   - Counts clients per radio band
   - Extracts channel utilization
   - Computes 5GHz SNR (`rxLastRssi − noiseFloor`) and TX retry rate
   - Evaluates Critical RF indicators when client thresholds are met

4. **Data Delivery**:
   - Formats metrics for InsightFinder API
   - Sends to InsightFinder platform

### Instance Naming & Metadata

The agent maintains a device lookup cache (`devicelookup.json`, refreshed every 24 hours) built from the Device Inventory API, queried by equipment MAC address.

Instance name priority:

1. `MAC E0-01-A6-80-80-9A` — equipment MAC address (uppercase, colons replaced by dashes)
2. `SERIAL <serial>` — equipment serial from NetExperience, then from device inventory
3. `JIRAKEY <object_key>` — device inventory object key
4. Cleaned equipment name

Instance metadata sent with each metric payload (`im` field):

| Field | Source | Fallback |
|-------|--------|----------|
| Display name (`idn`) | NetExperience equipment name | `AP-Edgecore` |
| Component name (`cn`) | Inventory `manufacturer-device_class` (e.g. `Edgecore-AP`) | `AP-Edgecore` |
| Zone (`z`) | Inventory `meta.venue` | `UNKNOWN` |
| IP (`i`) | Inventory `ip_address` | NetExperience equipment IP |

### Metrics Collected

Per equipment (AP):

| Metric | Description | Threshold-gated |
|--------|-------------|-----------------|
| `Total Clients` | Total connected clients | — |
| `Clients 5GHz` | Clients on 5GHz band | — |
| `Clients 2.4GHz` | Clients on 2.4GHz band | — |
| `Channel Utilization 5GHz` | 5GHz channel utilization % | — |
| `Channel Utilization 2.4GHz` | 2.4GHz channel utilization % | — |
| `Average RSSI` | Average RSSI across all clients (dBm, absolute value) | — |
| `WAN Port Speed Mbps` | WAN port speed | — |
| `% Clients RSSI < -74 dBm` | % of clients in orange signal zone | `min_clients_rssi_threshold` |
| `% Clients RSSI < -78 dBm` | % of clients in red signal zone | `min_clients_rssi_threshold` |
| `% Clients RSSI < -80 dBm` | % of clients below red signal zone | `min_clients_rssi_threshold` |
| `SNR 5GHz` | 5GHz SNR: `rxLastRssi − noiseFloor` (dB) | `min_clients_snr_threshold` |
| `TX Retry Rate 5GHz` | 5GHz TX retry rate: `retries / frames × 100` (%) | `min_clients_snr_threshold` |
| `≥ 35% of clients RSSI < -78 dBm AND SNR/SINR < 18 dB` | Critical RF binary indicator | both thresholds |
| `≥ 35% of clients RSSI < -78 dBm AND Airtime Utilization > 85%` | Critical RF binary indicator | `min_clients_rssi_threshold` |
| `≥ 35% of clients RSSI < -78 dBm AND TX Retry Rate > 18%` | Critical RF binary indicator | both thresholds |

Threshold-gated metrics are **omitted entirely** (not sent as zero) when the AP has fewer clients than the configured minimum.

### Critical RF Indicators

Each indicator is `1` when its specific pair of conditions is simultaneously true, otherwise `0`. They are evaluated independently — multiple can fire at once.

The RSSI condition is always: **≥ 35% of clients have RSSI < −78 dBm** (requires ≥ `min_clients_rssi_threshold` clients).

| Metric name sent to InsightFinder | Paired KPI condition | Additional threshold |
|-----------------------------------|----------------------|----------------------|
| `≥ 35% of clients RSSI < -78 dBm AND SNR/SINR < 18 dB` | SNR 5GHz < 18 dB | `min_clients_snr_threshold` |
| `≥ 35% of clients RSSI < -78 dBm AND Airtime Utilization > 85%` | Channel Utilization 5GHz > 85% | — |
| `≥ 35% of clients RSSI < -78 dBm AND TX Retry Rate > 18%` | TX Retry Rate 5GHz > 18% | `min_clients_snr_threshold` |

## Rate Limiting

The agent implements token bucket rate limiting:
- Default: 180 requests per 10 seconds
- Automatically waits when the limit is reached
- Configurable via `rate_limit_requests` and `rate_limit_period`

## Logging

Logs include:
- Authentication events (login, refresh)
- Cache refresh operations
- Metric collection cycles
- API errors and retries
- Data delivery status

Log level configurable via `agent.log_level`: `debug`, `info`, `warn`, `error`

## Troubleshooting

### Authentication Issues
- Check credentials in `config.yaml`
- Verify network connectivity to NetExperience API
- Check logs for specific error messages

### No Metrics Collected
- Ensure customers and equipment are cached (check logs)
- Verify equipment has recent data in the API
- Check time range calculation (`fromTime`/`toTime`)

### Critical RF / SNR / TX Retry metrics missing
- These are omitted when the AP client count is below the configured threshold
- Check `min_clients_rssi_threshold` (controls RSSI % and Critical RF metrics) and `min_clients_snr_threshold` (controls SNR, TX Retry Rate, and SNR/TxRetry-paired Critical RF indicators)
- Default is 10 for both; APs with fewer clients will not emit these metrics

### Rate Limiting
- Reduce `equipment_batch_size` if hitting rate limits
- Increase `rate_limit_period` for more conservative limiting
- Check logs for "rate limiter" messages

## Development

### Adding New Metrics

1. Update `models.EquipmentMetrics` in `pkg/models/models.go`
2. Add processing logic in `worker/process.go:processEquipmentMetrics()`
3. Add metric to send list in `worker/process.go:sendMetricBatch()`

### Testing

Run locally with verbose logging:
```bash
# Set log_level: debug in configs/config.yaml
./netexperience-agent
```

## License

Copyright InsightFinder Inc.
