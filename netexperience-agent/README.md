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
  - RSSI statistics and thresholds
  - Client distribution across signal strength levels

## Architecture

```
netexperience-agent/
├── configs/          # Configuration management
├── insightfinder/    # InsightFinder API client (copied from positron-agent)
├── netexperience/    # NetExperience API client
│   ├── netexperience.go  # Authentication and token management
│   ├── util.go          # API client methods
│   ├── cache.go         # Cache management
│   └── type.go          # Type definitions
├── pkg/models/       # Data models
├── worker/           # Main processing logic
│   ├── worker.go     # Worker lifecycle
│   └── process.go    # Metric processing
└── main.go          # Entry point
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
  
  # Thresholds
  min_clients_rssi_threshold: 10

insightfinder:
  server_url: https://stg.insightfinder.com
  username: your-username
  license_key: your-license-key
  metrics_project_name: NetExperience-Metrics
  sampling_interval: 60
```

**Note:** The agent will automatically create the InsightFinder project if it doesn't exist. You don't need to manually create the project in the InsightFinder UI first.

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

1. **Initial Login**: Agent logs in using username/password to get access token
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

4. **Data Delivery**:
   - Formats metrics for InsightFinder API
   - Sends to InsightFinder platform
   - Instance naming: `{EquipmentName}`

### Metrics Collected

Per equipment (AP):
- `total_clients`: Total connected clients
- `clients_5ghz`: Clients on 5GHz band
- `clients_2_4ghz`: Clients on 2.4GHz band
- `channel_utilization_5ghz`: 5GHz channel utilization %
- `channel_utilization_2_4ghz`: 2.4GHz channel utilization %
- `average_rssi`: Average RSSI across all clients
- `clients_rssi_below_74`: Count of clients with RSSI < -74 dBm
- `clients_rssi_below_78`: Count of clients with RSSI < -78 dBm
- `clients_rssi_below_80`: Count of clients with RSSI < -80 dBm
- `percent_rssi_below_74`: Percentage of clients with RSSI < -74 dBm
- `percent_rssi_below_78`: Percentage of clients with RSSI < -78 dBm
- `percent_rssi_below_80`: Percentage of clients with RSSI < -80 dBm

**Note**: RSSI percentages are only calculated when total clients >= `min_clients_rssi_threshold` (default: 10)

## Rate Limiting

The agent implements token bucket rate limiting:
- Default: 180 requests per 10 seconds
- Automatically waits when limit is reached
- Configurable via `rate_limit_requests` and `rate_limit_period`

## Logging

Logs include:
- Authentication events (login, refresh)
- Cache refresh operations
- Metric collection cycles
- API errors and retries
- Data delivery status

Log level configurable via `agent.log_level`: DEBUG, INFO, WARN, ERROR

## Troubleshooting

### Authentication Issues
- Check credentials in config.yaml
- Verify network connectivity to NetExperience API
- Check logs for specific error messages

### No Metrics Collected
- Ensure customers and equipment are cached (check logs)
- Verify equipment has recent data in the API
- Check time range calculation (fromTime/toTime)

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
# Set log level to DEBUG in config.yaml
./netexperience-agent
```

## License

Copyright InsightFinder Inc.
