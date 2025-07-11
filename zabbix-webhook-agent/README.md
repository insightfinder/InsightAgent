# Zabbix Webhook Agent

A FastAPI-based HTTP server for processing Zabbix webhooks and forwarding alert data to InsightFinder for enhanced monitoring and analytics.

## Overview

The Zabbix Webhook Agent acts as a bridge between Zabbix monitoring systems and InsightFinder, providing:
- Secure webhook processing with API key authentication
- Data transformation and enrichment of Zabbix alerts
- Multi-project configuration support
- Health monitoring and metrics collection
- Docker containerization for easy deployment

## Features

- **Webhook Processing**: Receives and processes Zabbix webhook data
- **Authentication**: Secure API key-based authentication
- **Multi-Configuration**: Support for multiple InsightFinder project configurations
- **Data Enrichment**: Enhances alert data before forwarding
- **Health Monitoring**: Built-in health checks and status endpoints
- **Metrics Collection**: Tracks webhook processing statistics
- **Docker Support**: Containerized deployment with Docker Compose
- **Configuration Management**: Dynamic configuration loading and reloading

## Quick Start

### Using Docker Compose (Recommended)

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd zabbix-webhook-agent
   ```

2. Copy and configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. Start the server:
   ```bash
   docker-compose up -d
   ```

### Using the Enhanced Start Script (Recommended for Production)

The enhanced start script provides full service management capabilities:

1. **Installation and Setup**:
   ```bash
   chmod +x start.sh
   ./start.sh install
   ```

2. **Service Management**:
   ```bash
   # Start the service
   ./start.sh start
   
   # Stop the service
   ./start.sh stop
   
   # Restart the service
   ./start.sh restart
   
   # Check service status
   ./start.sh status
   
   # View service logs
   ./start.sh logs
   ```

3. **Development Mode**:
   ```bash
   # Run in development mode (no systemd)
   ./start.sh dev
   ```

4. **Other Commands**:
   ```bash
   # Uninstall the service
   ./start.sh uninstall
   
   # Show help
   ./start.sh help
   ```

#### Features of the Enhanced Script:
- **Systemd Service Management**: Automatically creates and manages systemd service
- **Service Status Checking**: Checks if server is already running
- **Auto-configuration**: Sets up virtual environment, dependencies, and service files
- **User Management**: Runs service as current user (non-root)
- **Log Management**: Easy access to service logs via journalctl
- **Development Mode**: Option to run without systemd for development

### Basic Start Script Usage

For simple development usage:
```bash
chmod +x start.sh
./start.sh dev

## Configuration

### Environment Variables

Create a `.env` file based on `.env.example`:

```bash
API_KEY=your_secret_api_key_here
LOG_LEVEL=INFO
```

### InsightFinder Configuration

The server supports multiple InsightFinder configurations stored in the `config/insightfinder/` directory. Each configuration file should contain:

- Base URL
- Project name
- Username/Password or License Key
- Other project-specific settings

#### Stream Control Options

The server provides fine-grained control over which types of alerts are sent to InsightFinder:

- **`stream_resolved_alerts`** (boolean, default: `true`): Controls whether RESOLVED alerts are sent to the InsightFinder `/api/v1/customprojectrawdata` endpoint
  - When set to `true`: Both PROBLEM and RESOLVED alerts are sent to InsightFinder
  - When set to `false`: Only PROBLEM alerts are sent to InsightFinder, but incident investigation API is still called for RESOLVED events

#### Configuration File Example

```ini
[insightfinder]
base_url = https://app.insightfinder.com
username = your_username
password = your_password
license_key = your_license_key
project_name = your_project_name
system_name = your_system_name

[project_settings]
instance_type = Zabbix
project_cloud_type = Zabbix
data_type = Log
insight_agent_type = Custom
sampling_interval = 60
sampling_interval_in_seconds = 60
# Control resolved alert streaming
stream_resolved_alerts = true
```

#### Environment Variable Configuration

For legacy `.env` file configuration, add:
```bash
STREAM_RESOLVED_ALERTS=true
```

## API Endpoints

### Public Endpoints

- `GET /` - API information
- `GET /health` - Health check endpoint

### Authenticated Endpoints (require API key)

- `POST /webhook/zabbix` - Process Zabbix webhook (default config)
- `POST /webhook/zabbix/{config_name}` - Process webhook with specific config
- `POST /webhook/test` - Test webhook processing without forwarding
- `GET /status` - Server status and configuration
- `GET /configs` - List all available configurations
- `GET /configs/{config_name}` - Get specific configuration details
- `POST /configs/reload` - Reload configurations from disk

### Authentication

Include the API key in the request header:
```
X-API-Key: your_secret_api_key_here
```

## Project Structure

```
zabbix-webhook-agent/
├── main.py                     # Main FastAPI application
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker configuration
├── docker-compose.yml          # Docker Compose setup
├── start.sh                    # Startup script
├── config/                     # Configuration files
│   ├── enhanced_zabbix_media_script.js
│   └── insightfinder/          # InsightFinder configurations
├── src/                        # Source code
│   ├── clients/                # External service clients
│   ├── core/                   # Core functionality
│   ├── processors/             # Data processing logic
│   └── utils/                  # Utility functions
└── docs/                       # Documentation
```

## Development

### Prerequisites

- Python 3.11+
- pip
- Docker (optional)

### Installation

1. Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

4. Run the development server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 80 --reload
   ```

### API Documentation

Once running, access the interactive API documentation at:
- Swagger UI: `http://localhost:80/docs`
- ReDoc: `http://localhost:80/redoc`

## Health Monitoring

The server provides health check endpoints for monitoring:

- `GET /health` - Returns server health status
- Docker health checks are configured for container monitoring

## Logging

Logs are configured with structured formatting and can be controlled via the `LOG_LEVEL` environment variable. Supported levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.
