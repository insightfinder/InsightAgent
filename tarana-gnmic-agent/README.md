# Tarana gNMIc Agent

Comprehensive monitoring agent for Tarana Wireless network devices that collects metrics via gNMIc telemetry, stores them in InfluxDB, and forwards to InsightFinder for advanced analytics.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Tarana Network Devices                       │
│                  (BN - Base Nodes, RN - Remote Nodes)           │
└────────────────────────────┬────────────────────────────────────┘
                             │ gNMI Telemetry
                             ▼
                    ┌─────────────────┐
                    │  gNMIc Listener  │
                    │  (Port 80)       │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │    InfluxDB      │
                    │  (Time Series DB)│
                    └────────┬─────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Metrics Collector│
                    │   (Go Service)   │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  InsightFinder   │
                    │   (Analytics)    │
                    └──────────────────┘
```

## 📁 Directory Structure

```
tarana-gnmic-agent/
├── config/
│   └── config.yaml              # Central configuration file
├── gnmic/
│   ├── gnmicc                   # gNMIc binary
│   ├── telemetry_cfg.yaml       # gNMIc telemetry configuration
│   └── gnmic.pid                # Process ID file (created at runtime)
├── influxdb/
│   └── docker-compose.yml       # InfluxDB Docker configuration
├── collector/
│   └── collector.go             # Metrics collection logic
├── insightfinder/
│   └── sender.go                # InsightFinder integration
├── logs/
│   ├── agent.log                # Structured agent logs
│   ├── nohup.log                # Main stdout/stderr
│   ├── gnmic.log                # gNMIc logs
│   └── monitor.log              # Cron monitor logs
├── main.go                      # Main agent application
├── go.mod                       # Go module definition
├── start.sh                     # Start all services
├── stop.sh                      # Stop all services
├── status.sh                    # Check service status
├── setup-cron.sh                # Setup automatic monitoring
└── README.md                    # This file
```

## 🚀 Quick Start

### Prerequisites

- **Go 1.21+** installed
- **Docker** and **Docker Compose** installed
- **sudo** access (for running gNMIc on port 80)
- **Network access** to:
  - Tarana devices (for telemetry)
  - InsightFinder API (if enabled)

### Installation

1. **Navigate to the agent directory:**
   ```bash
   cd tarana-gnmic-agent
   ```

2. **Configure the agent:**
   Edit `config/config.yaml` with your settings:
   ```bash
   nano config/config.yaml
   ```
   
   Key settings to update:
   - `insightfinder.user_name` - Your InsightFinder username
   - `insightfinder.license_key` - Your InsightFinder license key
   - `insightfinder.metrics_project_name` - Project name in InsightFinder
   - `insightfinder.sampling_interval` - How often to collect/send data (seconds)

3. **Build dependencies:**
   ```bash
   go mod download
   go build -o tarana-gnmic-agent
   ```

4. **Start all services:**
   ```bash
   ./start.sh
   ```

That's it! The agent is now running.

## 🎛️ Configuration

### Main Configuration File: `config/config.yaml`

```yaml
# Agent Settings
agent:
  name: "tarana-gnmic-agent"
  log_level: "info"           # debug, info, warn, error
  log_file: "logs/agent.log"

# InfluxDB Configuration
influxdb:
  url: "http://localhost:9092"
  token: "my-super-secret-auth-token"
  org: "tarana"
  bucket: "gnmic-data"

# gNMIc Telemetry Configuration
gnmic:
  listen_address: ":80"
  org: "tarana"
  auto_start: true

# Metrics Collector Configuration
collector:
  time_range: "-5m"            # Query last 5 minutes of data

# InsightFinder Configuration
insightfinder:
  enabled: true
  server_url: "https://app.insightfinder.com"
  user_name: "your-username"
  license_key: "your-license-key"
  metrics_project_name: "tarana-gnmic-metrics"
  metrics_system_name: "tarana-network"
  sampling_interval: 60        # Collect and send every 60 seconds
  cloud_type: "PrivateCloud"
  instance_type: "Tarana"
```

## 📊 Collected Metrics

### Remote Node (RN) Devices
| Metric | Description | Type |
|--------|-------------|------|
| `hostname` | Device hostname | String (used as instanceName) |
| `dl_snr` | Downlink Signal-to-Noise Ratio | Float |
| `ul_snr` | Uplink Signal-to-Noise Ratio | Float |
| `path_loss` | RF path loss | Float |
| `rf_range` | RF range distance | Float |
| `rx_signal_0` | RX signal level (radio 0) | Float |
| `rx_signal_1` | RX signal level (radio 1) | Float |
| `rx_signal_2` | RX signal level (radio 2) | Float |
| `rx_signal_3` | RX signal level (radio 3) | Float |

### Base Node (BN) Devices
| Metric | Description | Type |
|--------|-------------|------|
| `hostname` | Device hostname | String (used as instanceName) |
| `active_connections` | Number of active client connections | Integer |
| `rx_signal_0` | RX signal level (radio 0) | Float |
| `rx_signal_1` | RX signal level (radio 1) | Float |
| `rx_signal_2` | RX signal level (radio 2) | Float |
| `rx_signal_3` | RX signal level (radio 3) | Float |

### InsightFinder Data Format
- **instanceName**: Device hostname
- **componentName**: Empty (as per requirement)
- **IP**: Extracted from source (port removed)
- **timestamp**: Unix milliseconds
- **data**: Dictionary of metrics (all converted to float/int)

## 🛠️ Management Scripts

### Start Services
```bash
./start.sh
```
Starts all three services:
1. InfluxDB (Docker container)
2. gNMIc telemetry listener (port 80)
3. Tarana gNMIc Agent (metrics collector and forwarder)

### Stop Services
```bash
./stop.sh
```
Gracefully stops all services in reverse order.

### Check Status
```bash
./status.sh
```
Shows the status of all services and recent log entries.

### Setup Automatic Monitoring
```bash
./setup-cron.sh
```
Sets up a cron job that:
- Runs every 5 minutes
- Checks if all services are running
- Automatically restarts any stopped services
- Logs all actions to `logs/monitor.log`

## 📝 Logs

All logs are centralized in the `logs/` directory:

| Log File | Description | Command to View |
|----------|-------------|-----------------|
| `nohup.log` | Main agent stdout/stderr | `tail -f logs/nohup.log` |
| `agent.log` | Structured agent logs (logrus) | `tail -f logs/agent.log` |
| `gnmic.log` | gNMIc telemetry logs | `tail -f logs/gnmic.log` |
| `monitor.log` | Cron monitor logs | `tail -f logs/monitor.log` |

**View all logs simultaneously:**
```bash
tail -f logs/*.log
```

## 🔧 Advanced Usage

### Manual Build
```bash
go build -o tarana-gnmic-agent
```

### Run with Custom Config
```bash
./tarana-gnmic-agent --config /path/to/config.yaml
```

### Run in Foreground (for debugging)
```bash
./tarana-gnmic-agent --config config/config.yaml
```

### Test Metrics Collection Only
```bash
# Disable InsightFinder in config.yaml
insightfinder:
  enabled: false

# Then start the agent
./start.sh
```

## 🐛 Troubleshooting

### Check if services are running
```bash
./status.sh
```

### gNMIc not receiving telemetry
1. Check if port 80 is accessible:
   ```bash
   sudo netstat -tulpn | grep :80
   ```

2. Verify telemetry configuration on Tarana devices

3. Check gNMIc logs:
   ```bash
   tail -f logs/gnmic.log
   ```

### InfluxDB not starting
1. Check Docker status:
   ```bash
   docker ps -a | grep influxdb
   ```

2. View Docker logs:
   ```bash
   docker logs influxdb
   ```

3. Ensure port 9092 is not in use:
   ```bash
   sudo netstat -tulpn | grep :9092
   ```

### Agent not collecting metrics
1. Check agent logs:
   ```bash
   tail -f logs/agent.log
   ```

2. Verify InfluxDB connectivity:
   ```bash
   curl -I http://localhost:9092/health
   ```

3. Check if data exists in InfluxDB:
   ```bash
   # Open InfluxDB UI
   firefox http://localhost:9092
   # Login: admin / adminpassword
   # Check bucket: gnmic-data
   ```

### InsightFinder not receiving data
1. Verify configuration:
   ```bash
   grep -A 10 "insightfinder:" config/config.yaml
   ```

2. Check network connectivity:
   ```bash
   curl -I https://app.insightfinder.com
   ```

3. Enable debug logging:
   ```yaml
   agent:
     log_level: "debug"
   ```

4. Restart agent:
   ```bash
   ./stop.sh && ./start.sh
   ```

## 📈 Performance

- **Memory Usage**: ~50-100 MB (agent only)
- **CPU Usage**: <5% (during collection cycles)
- **Network**: Minimal (depends on number of devices)
- **Disk Usage**: Logs rotate, InfluxDB data depends on retention

## 🔄 Data Flow

1. **Telemetry Reception** (continuous):
   - Tarana devices stream telemetry to gNMIc (port 80)
   - gNMIc writes to InfluxDB

2. **Metrics Collection** (periodic, based on `sampling_interval`):
   - Agent queries InfluxDB for last 5 minutes
   - Collects RN and BN device metrics
   - Ensures data integrity (hostname-based filtering)

3. **Data Transformation**:
   - Converts device metrics to InsightFinder format
   - Extracts IP from source (removes port)
   - Converts all numeric values to float64/int
   - Aligns timestamps to sampling interval

4. **Data Forwarding**:
   - Sends to InsightFinder via HTTP API
   - Retries on failure (3 attempts)
   - Logs all operations

## 🔒 Security Considerations

- gNMIc runs as **root** (required for port 80)
- InfluxDB uses **authentication** (admin/adminpassword)
- InsightFinder uses **license key** authentication
- All credentials in `config/config.yaml` - **protect this file**
- Consider using **environment variables** for sensitive data

## 📦 Dependencies

- **Go Packages**:
  - `github.com/sirupsen/logrus` - Structured logging
  - `gopkg.in/yaml.v3` - YAML configuration

- **External Services**:
  - Docker (for InfluxDB)
  - InfluxDB 2.7
  - gNMIc binary (included)

## 🤝 Support

For issues or questions:
1. Check logs in `logs/` directory
2. Run `./status.sh` to verify services
3. Review this README for troubleshooting steps

## 📄 License

This software is provided as-is for use with Tarana Wireless systems.

## 🔄 Updates and Maintenance

### Updating Configuration
1. Edit `config/config.yaml`
2. Restart services: `./stop.sh && ./start.sh`

### Updating the Agent
1. Pull latest code
2. Rebuild: `go build -o tarana-gnmic-agent`
3. Restart: `./stop.sh && ./start.sh`

### Log Rotation
Consider setting up log rotation:
```bash
sudo nano /etc/logrotate.d/tarana-gnmic-agent
```

Add:
```
/path/to/tarana-gnmic-agent/logs/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
```

---

**Version**: 1.0.0  
**Last Updated**: December 2025
