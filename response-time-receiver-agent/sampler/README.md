# Periodic Sampler Module

## Overview

The sampler module provides a periodic heartbeat/sampling service that sends configurable metric data to both staging and production environments. This is useful for maintaining a continuous data stream and ensuring that InsightFinder receives regular updates even when there's no actual metric activity.

## Features

- **Configurable Sampling Interval**: Set the frequency of data sending (e.g., 1 minute, 5 minutes)
- **Configurable Metrics**: Define which metrics to send and their values in the config file
- **Environment Coverage**: Automatically sends to both staging and production environments
- **Flexible Values**: Can send any metric value (typically 0 for heartbeat)
- **Non-blocking**: Runs as a goroutine, doesn't interfere with main receiver operations
- **Graceful Shutdown**: Properly stops when the application shuts down
- **Disabled by Default**: Must be explicitly enabled in configuration

## Configuration

The sampler is configured in the main `configs/config.yaml` file under the `sampler` section:

```yaml
sampler:
  enabled: false                                      # Set to true to enable periodic sampling
  sampling_interval: 300                              # Interval in seconds (300s = 5 minutes, 60s = 1 minute)
  server_url: "http://localhost:8080/api/v1/data"     # Receiver server URL to send data to
  metrics:                                            # Configurable metrics to send
    ServiceNowTicketCreateDelay: 0                    # ServiceNow Ticket Creation metric
    ServiceNowNoteRetrieve: 0                         # ServiceNow Feedback metric
```

### Configuration Parameters

- **enabled** (boolean, default: `false`): 
  - Set to `true` to enable the periodic sampler
  - Set to `false` to disable it (default behavior)

- **sampling_interval** (integer, default: `300`): 
  - Interval in seconds between each sample
  - Common values:
    - `60` = 1 minute
    - `300` = 5 minutes
    - `600` = 10 minutes

- **server_url** (string, default: `"http://localhost:8080/api/v1/data"`):
  - The URL of the receiver server to send data to
  - Should point to the `/api/v1/data` endpoint
  - For local testing: `http://localhost:8080/api/v1/data`
  - For remote servers: `http://your-server:port/api/v1/data`

- **metrics** (map, default: empty):
  - Key-value pairs of metric names and their values
  - Typically set to 0 for heartbeat/sampling purposes
  - You can add or remove metrics as needed
  - Example:
    ```yaml
    metrics:
      ServiceNowTicketCreateDelay: 0
      ServiceNowNoteRetrieve: 0
      CustomMetric: 10
    ```

## How It Works

1. When the application starts, it checks if the sampler is enabled
2. If enabled, it starts a goroutine that:
   - Sends an immediate first sample
   - Sets up a ticker based on the configured interval
   - Periodically sends samples with metric value 0
3. For each sample, it:
   - Creates a payload with `agentType: 0` (ServiceNow response)
   - Sets both metrics to value 0
   - Sends to both staging and production environments
   - Logs the activity (debug level for successful sends)
4. When the application shuts down, the sampler stops gracefully

## Sample Payload

The sampler sends the following JSON payload to the receiver:

```json
{
  "agentType": 0,
  "environment": "staging",
  "timestamp": 1733774400000,
  "metriclist": [
    {
      "name": "ServiceNowTicketCreateDelay",
      "value": 0
    },
    {
      "name": "ServiceNowNoteRetrieve",
      "value": 0
    }
  ]
}
```

Note: The metrics are converted from the config map format to the receiver's expected array format automatically.

## Usage Examples

### Enable with 5-minute interval and both metrics
```yaml
sampler:
  enabled: true
  sampling_interval: 300
  server_url: "http://localhost:8080/api/v1/data"
  metrics:
    ServiceNowTicketCreateDelay: 0
    ServiceNowNoteRetrieve: 0
```

### Enable with 1-minute interval and only one metric
```yaml
sampler:
  enabled: true
  sampling_interval: 60
  server_url: "http://localhost:8080/api/v1/data"
  metrics:
    ServiceNowTicketCreateDelay: 0
```

### Enable with custom metric values
```yaml
sampler:
  enabled: true
  sampling_interval: 300
  server_url: "http://localhost:8080/api/v1/data"
  metrics:
    ServiceNowTicketCreateDelay: 0
    ServiceNowNoteRetrieve: 0
    CustomHealthCheck: 1
```

### Disable (default)
```yaml
sampler:
  enabled: false
  sampling_interval: 300
  server_url: "http://localhost:8080/api/v1/data"
  metrics:
    ServiceNowTicketCreateDelay: 0
    ServiceNowNoteRetrieve: 0
```

## Logs

When enabled, the sampler produces the following logs:

- **Info**: `Starting sampler service with interval: X seconds`
- **Debug**: `Sending periodic sample with metric value 0`
- **Debug**: `Successfully sent sample for environment: staging/production`
- **Warning**: `Environment 'X' not found in configuration, skipping`
- **Error**: `Failed to send sample for environment 'X': error message`
- **Info**: `Stopping sampler service...`
- **Info**: `Sampler service stopped`

To see debug logs, set the log level to `DEBUG` in the agent configuration:

```yaml
agent:
  log_level: "DEBUG"
```

## Architecture

```
main.go
  ├─> Creates SamplerService
  ├─> Calls Start() (non-blocking, starts goroutine)
  └─> Calls Stop() on shutdown

SamplerService.Start()
  └─> Spawns goroutine
      ├─> Sends immediate first sample
      └─> Starts ticker loop
          └─> Every interval: sendSample()
              ├─> Sends to staging
              └─> Sends to production
```

## Integration with Receiver

The sampler sends data to the same receiver endpoint (`/api/v1/data`) that external agents use. The receiver processes it normally:

1. Receives the payload
2. Identifies it as ServiceNow response data (`agentType: 0`)
3. Processes metrics for the specified environment
4. Maps metrics using `metriclistMap` from config
5. Sends to InsightFinder

This ensures that the zero-value metrics flow through the same pipeline as real metrics, maintaining consistency in the data stream.

## Testing

To test the sampler:

1. Enable it in the config with a short interval (e.g., 60 seconds)
2. Start the receiver agent
3. Check logs for sampler activity
4. Verify that data appears in InsightFinder for both environments

```bash
# Edit config to enable sampler
vi configs/config.yaml

# Run the receiver agent
go run main.go

# Watch logs for sampler activity
# You should see: "Starting sampler service with interval: X seconds"
```
