# InsightFinder Receiver Agent

A lightweight HTTP server for receiving metric data from external agents and forwarding it to InsightFinder platform. Built with Go and Fiber framework.

## Features

- **Multi-Environment Support**: Configure multiple environments (staging, production, nbc) with independent InsightFinder projects
- **Agent Type Processing**: Support for different agent types (ServiceNow Response, Custom)
- **Metric Mapping**: Flexible metric name mapping via configuration
- **High Performance**: Built on Fiber framework for fast HTTP handling
- **Structured Logging**: Uses Logrus for comprehensive logging
- **Health Checks**: Built-in health check endpoint for monitoring
- **Graceful Shutdown**: Proper cleanup on shutdown
- **Auto Project Creation**: Automatically creates InsightFinder projects if they don't exist

## Architecture

```
┌─────────────────┐
│ External Agent  │
│ (ServiceNow)    │
└────────┬────────┘
         │ HTTP POST
         ▼
┌─────────────────────┐
│  Receiver Agent     │
│  - Parse Request    │
│  - Map Metrics      │
│  - Route to Env     │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  InsightFinder      │
│  - Staging          │
│  - Production       │
│  - NBC              │
└─────────────────────┘
```

## Installation

### Prerequisites

- Go 1.21 or higher
- Access to InsightFinder platform

## Configuration

Edit `configs/config.yaml`:

```yaml
agent:
  server_port: 8080
  log_level: "INFO"  # DEBUG, INFO, WARN, ERROR

environment:
  send_to_all_environments: false  # true = send to all envs if environment field is empty
  
  staging:
    insightfinder:
      server_url: https://nbc.insightfinder.com
      username: your-username
      license_key: your-license-key
      metrics_project_name: receiver-Metrics
      metrics_system_name: ReceiverAgent
      sampling_interval: 60
    metriclistMap:
      service_now_creation_time: "Service Now Creation Time"
      service_now_feedback_time: "Service Now Feedback Time"
      
  production:
    # ... similar configuration
    
  nbc:
    # ... similar configuration
```

### Configuration Parameters

- **agent.server_port**: HTTP server port (default: 8080)
- **agent.log_level**: Logging level (DEBUG, INFO, WARN, ERROR)
- **environment.send_to_all_environments**: Send to all environments if no environment specified
- **metriclistMap**: Maps incoming metric names to InsightFinder metric names

## Usage

### Start the Server

```bash
# Using default config path
./receiver-agent

# Using custom config path
./receiver-agent -config /path/to/config.yaml
```

### API Endpoints

#### Health Check

```bash
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime": "1h30m45s"
}
```

#### Data Ingestion

```bash
POST /api/v1/data
Content-Type: application/json
```

**Request Body:**
```json
{
  "environment": "staging",
  "timestamp": 1700000000000,
  "agentType": 0,
  "metriclist": [
    {
      "name": "service_now_creation_time",
      "value": 150.5
    },
    {
      "name": "service_now_feedback_time",
      "value": 200.3
    }
  ]
}
```

**Request Fields:**
- `environment` (string): Target environment (staging, production, nbc, or empty for all)
- `timestamp` (number): 13-digit epoch timestamp in milliseconds
- `agentType` (number): Agent type enum (0 = ServiceNow Response, 1 = Custom)
- `metriclist` (array): Array of metric objects with name and value

**Response (Success):**
```json
{
  "success": true,
  "message": "Successfully sent metrics to 1 environment(s): [staging]",
  "data": {
    "environments_processed": ["staging"],
    "success_count": 1,
    "failed_environments": []
  }
}
```

**Response (Error):**
```json
{
  "success": false,
  "message": "Invalid request format: ..."
}
```

### Agent Types

| Value | Type | Description |
|-------|------|-------------|
| 0 | ServiceNow Response | Processes ServiceNow response metrics |
| 1 | Custom | Custom agent processing (placeholder) |
| 2+ | Future | Reserved for future agent types |

## Examples

### Example 1: Send ServiceNow Metrics to Staging

```bash
curl -X POST http://localhost:8080/api/v1/data \
  -H "Content-Type: application/json" \
  -d '{
    "environment": "staging",
    "timestamp": 1700000000000,
    "agentType": 0,
    "metriclist": [
      {"name": "service_now_creation_time", "value": 150.5},
      {"name": "service_now_feedback_time", "value": 200.3}
    ]
  }'
```

### Example 2: Send to All Environments

Set `send_to_all_environments: true` in config, then:

```bash
curl -X POST http://localhost:8080/api/v1/data \
  -H "Content-Type: application/json" \
  -d '{
    "environment": "",
    "timestamp": 1700000000000,
    "agentType": 0,
    "metriclist": [
      {"name": "service_now_creation_time", "value": 150.5}
    ]
  }'
```

### Example 3: Health Check

```bash
curl http://localhost:8080/health
```

## Metric Mapping

The agent uses `metriclistMap` to transform incoming metric names to InsightFinder metric names:

**Incoming Metric Name** → **InsightFinder Metric Name**

For example:
- `service_now_creation_time` → `Service Now Creation Time`
- `service_now_feedback_time` → `Service Now Feedback Time`

Only metrics defined in `metriclistMap` will be sent to InsightFinder. Others are ignored.

## Multi-Environment Support

The agent supports routing metrics to different InsightFinder environments:

1. **Explicit Environment**: Set `environment` field in request
2. **Send to All**: Set `send_to_all_environments: true` and leave `environment` empty
3. **Environment Validation**: Invalid environments are rejected with error

## Development

### Project Structure

```
receiver-agent/
├── main.go                  # Application entry point
├── go.mod                   # Go module dependencies
├── configs/
│   ├── config.yaml          # Configuration file
│   ├── type.go              # Configuration types
│   └── config.go            # Configuration loader
├── receiver/
│   ├── types.go             # Request/response types
│   ├── handlers.go          # HTTP handlers
│   └── servicenow_processor.go  # ServiceNow processing
└── insightfinder/
    ├── types.go             # InsightFinder types
    └── insightfinder.go     # InsightFinder client
```

## Logging

The agent uses structured logging with Logrus:

```
[2024-11-20 15:04:05] INFO Loading configuration from: configs/config.yaml
[2024-11-20 15:04:05] INFO Configuration loaded successfully
[2024-11-20 15:04:05] INFO Starting HTTP server on :8080
[2024-11-20 15:04:05] INFO Receiver agent started successfully on port 8080
[2024-11-20 15:04:10] INFO Received data ingestion request
[2024-11-20 15:04:10] INFO Processing ServiceNow response data for environment: staging
[2024-11-20 15:04:11] INFO Successfully sent metrics to InsightFinder
```

Set `log_level` in config to control verbosity:
- **DEBUG**: Detailed debug information
- **INFO**: General informational messages
- **WARN**: Warning messages
- **ERROR**: Error messages only

## Troubleshooting

### Common Issues

1. **Port already in use**
   - Change `server_port` in config.yaml
   - Kill process using the port: `lsof -ti:8080 | xargs kill`

2. **Invalid configuration**
   - Check YAML syntax
   - Ensure all required fields are set
   - Verify InsightFinder credentials

3. **Metrics not appearing in InsightFinder**
   - Check metric names match `metriclistMap`
   - Verify environment configuration
   - Check InsightFinder credentials and project names
   - Review logs for errors

4. **Connection refused**
   - Verify InsightFinder `server_url` is correct
   - Check network connectivity
   - Ensure firewall allows outbound HTTPS

### Debug Mode

Enable debug logging:

```yaml
agent:
  log_level: "DEBUG"
```

This will show:
- Detailed metric mapping
- HTTP request/response details
- InsightFinder API calls

## Performance

- **Concurrent Requests**: Fiber handles concurrent requests efficiently
- **Timeout Settings**: 30s read/write, 120s idle
- **Metric Batching**: Metrics sent per environment per request
- **Retry Logic**: 3 retries with 5s intervals for InsightFinder API

## Security Considerations

- **HTTPS**: Configure reverse proxy (nginx/Apache) for HTTPS
- **Authentication**: Add API key validation if needed
- **Rate Limiting**: Consider adding rate limiting middleware
- **Input Validation**: Request body is validated before processing

## License

Copyright © 2025 InsightFinder

## Support

For issues or questions:
- Check logs with `log_level: "DEBUG"`
- Review InsightFinder platform documentation
- Contact InsightFinder support
