# Elasticsearch Collector
Collects data from Elasticsearch and sends it to InsightFinder.

## Quick Start with Docker

1. **Configure the agent:**
   ```bash
   cp conf.d/config.ini.template conf.d/config.ini
   # Edit conf.d/config.ini with your Elasticsearch and InsightFinder settings
   ```

2. **Obfuscate password (if using authentication):**
   ```bash
   # Run interactively to obfuscate your Elasticsearch password
   docker run -it --rm elasticsearch-collector python3 ifobfuscate.py
   # Copy the obfuscated value to your config.ini http_auth field
   ```

3. **Build the Docker image:**
   ```bash
   docker build -t elasticsearch-collector .
   ```

4. **Run the container:**
   ```bash
   docker run -d \
     --name elasticsearch-collector \
     -v $(pwd)/conf.d:/app/conf.d:ro \
     -v $(pwd)/logs:/app/logs \
     elasticsearch-collector
   ```

5. **Monitor the agent:**
   ```bash
   # View container logs
   docker logs -f elasticsearch-collector
   
   # Check agent log files
   tail -f logs/*.log
   ```

6. **Stop/restart:**
   ```bash
   docker stop elasticsearch-collector
   docker start elasticsearch-collector
   docker restart elasticsearch-collector
   ```

### Docker Volume Mounts

- **`/app/conf.d`** - Configuration directory (required)
  - Contains `config.ini` and optional `query_json.json`
  - Mount as read-only (`:ro`) for security
  
- **`/app/logs`** - Log output directory (optional but recommended)
  - Persists agent logs on the host system
  - Useful for troubleshooting and monitoring

### Docker Advanced Usage

**Custom cron parameters:**
```bash
docker run -d \
  --name elasticsearch-collector \
  -v $(pwd)/conf.d:/app/conf.d:ro \
  -v $(pwd)/logs:/app/logs \
  elasticsearch-collector \
  /bin/bash -c "python3 cron.py -v -p 8 -o 15"
```

**Docker Compose:**
Create `docker-compose.yml`:
```yaml
version: '3.8'
services:
  elasticsearch-collector:
    build: .
    container_name: elasticsearch-collector
    volumes:
      - ./conf.d:/app/conf.d:ro
      - ./logs:/app/logs
    restart: unless-stopped
    environment:
      - TZ=UTC
```

Run with: `docker-compose up -d`

## Local Installation

### Prerequisites
- Python 3.6+ (Python 3.13 recommended)
- pip3

### Installation Steps

1. **Setup Python environment:**
   ```bash
   ./setup/configure_python.sh
   ```
   This script creates a virtual environment and installs all required dependencies.

2. **Configure the agent:**
   ```bash
   cp conf.d/config.ini.template conf.d/config.ini
   # Edit conf.d/config.ini with your Elasticsearch and InsightFinder settings
   ```

3. **Obfuscate password (if using authentication):**
   ```bash
   python3 ifobfuscate.py
   # Enter your password when prompted
   # Copy the obfuscated value to your config.ini http_auth field
   ```

4. **Test the configuration (recommended):**
   ```bash
   ./setup/test_agent.sh
   ```
   This connects to Elasticsearch but doesn't send data to InsightFinder - useful for validation.

5. **Run the agent:**
   ```bash
   nohup venv/bin/python3 cron.py &
   ```

6. **Monitor the agent:**
   ```bash
   # Check if running
   jobs -l
   
   # View logs
   tail -f logs/*.log
   ```

7. **Stop the agent:**
   ```bash
   # Get PID of background jobs
   jobs -l
   
   # Kill the cron process
   kill -9 <PID>
   ```

### Local Advanced Usage

**Run with custom parameters:**
```bash
# Verbose output, 8 processes, 15 second offset
nohup venv/bin/python3 cron.py -v -p 8 -o 15 &
```

**Command line options:**
- `-q, --quiet` - Only show warnings and errors
- `-v, --verbose` - Verbose output
- `-g, --grace` - Grace time in minutes (default: 1)
- `-o, --offset` - Offset time in seconds (default: 10)
- `-p, --process` - Max number of processes (default: 4)

## Configuration

The `conf.d/config.ini` file contains all settings needed to connect to Elasticsearch and stream data to InsightFinder.

### Quick Configuration Example

```ini
[elasticsearch]
es_uris = http://localhost:9200
indeces = filebeat*
http_auth = username:obfuscated_password
timestamp_field = @timestamp

[insightfinder]
user_name = your_email@example.com
license_key = your_license_key
project_name = my-elasticsearch-logs
project_type = log
sampling_interval = 1
run_interval = 1
```

### Config Variables

#### Elasticsearch Settings

* **`es_uris`** (Required)
  * Comma-delimited list of RFC-1738 formatted URLs
  * Format: `<scheme>://[<username>:<password>@]hostname:port`
  * Example: `http://localhost:9200` or `https://user:pass@es.example.com:9200`

* **`indeces`** (Required)
  * Indices to search over (supports regex/wildcards)
  * Example: `filebeat*`, `metricbeat-*`, or `logs-2024-*`

* **`query_json`** (Optional)
  * Query in JSON format for Elasticsearch
  * Use for filtering data (e.g., exclude DEBUG logs)
  * Not needed if providing `query_json_file`

* **`query_json_file`** (Optional)
  * Path to JSON file containing query body
  * File should be in `conf.d/` directory
  * Not needed if providing `query_json`

* **`query_chunk_size`** (Optional)
  * Maximum messages per query
  * Default: `5000`, Max: `10000`

* **`query_time_offset_seconds`** (Optional)
  * Time offset when querying live data relative to current time
  * Default: `0`

* **`http_auth`** (Optional)
  * Authentication in format `username:password`
  * **Use obfuscated password** (see `ifobfuscate.py`)
  * Overridden if credentials are in the URL

* **`port`** (Optional)
  * Port to connect to Elasticsearch
  * Overridden if port is in URL

* **`use_ssl`** (Optional)
  * Enable SSL: `True` or `False`
  * Automatically set to `True` if URI scheme is `https`

* **`ssl_version`** (Optional)
  * SSL version: `SSLv23` (default), `SSLv2`, `SSLv3`, `TLSv1`

* **`verify_certs`** (Optional)
  * Verify SSL certificates: `True` or `False`

* **`ssl_assert_hostname`** (Optional)
  * Enable hostname verification: `True` or `False`

* **`ssl_assert_fingerprint`** (Optional)
  * Enable fingerprint verification: `True` or `False`

* **`ca_certs`** (Optional)
  * Path to CA bundle

* **`client_cert`** (Optional)
  * Path to client certificate

* **`client_key`** (Optional)
  * Path to client key

* **`his_time_range`** (Optional)
  * Historical data time range for backfilling
  * Format: `YYYY-MM-DD HH:MM:SS,YYYY-MM-DD HH:MM:SS`
  * Example: `2024-04-14 00:00:00,2024-04-15 00:00:00`

* **`timestamp_field`** (Required)
  * Field name for the timestamp
  * Default: `@timestamp`
  * Use full path if `document_root_field` is empty (e.g., `_source.@timestamp`)

* **`timestamp_format`** (Optional)
  * Format in Python [arrow](https://arrow.readthedocs.io/en/latest/#supported-tokens) syntax
  * Use `epoch` for Unix timestamps
  * For split timestamps: `{YYYY-MM-DD} {HH:mm:ss} {ZZ}`
  * For multiple possible fields: `timestamp1,timestamp2`

* **`timezone`** (Optional)
  * Timezone of timestamp data (pytz format)
  * Required if timezone not included in Elasticsearch data
  * Example: `UTC`, `America/New_York`, `Europe/London`

* **`target_timestamp_timezone`** (Optional)
  * Timezone for data stored in InsightFinder
  * Default: `UTC`

* **`document_root_field`** (Optional)
  * Root field for document parsing
  * Default: `_source`
  * Use `""` for whole document as root

* **`instance_field`** (Optional)
  * Field name for instance identification
  * Example: `agent.hostname`, `host.name`
  * Falls back to Elasticsearch server name if not set

* **`instance_field_regex`** (Optional)
  * Field name and regex to extract instance name
  * Syntax: `<field1>::<regex1>,<field2>::<regex2>`
  * Example: `message::host=\"(.*?)\"`

* **`instance_whitelist`** (Optional)
  * Regex to filter instances

* **`default_instance_name`** (Optional)
  * Default instance name if not found

* **`component_field`** (Optional)
  * Field name for component identification

* **`default_component_name`** (Optional)
  * Default component name if not set

* **`device_field`** (Optional)
  * Field name for device/container (for containerized projects)
  * Can be priority list: `device1,device2`

* **`device_field_regex`** (Optional)
  * Regex with named group 'device': `(?P<device>.*)`

* **`data_fields`** (Optional)
  * Comma-delimited list of fields to send as data
  * Supports field names and regex patterns
  * If empty, entire document at root is sent
  * Example: `/^system\.filesystem.*/,system.cpu.total.pct`

* **`aggregation_data_fields`** (Optional)
  * Fields to aggregate (string or regex, comma-separated)
  * Example: `/0-metric\.values\.99.0/,value,doc_count`

* **`project_field`** (Optional)
  * Field name for project identification
  * If empty, uses `project_name` from InsightFinder section

* **`project_whitelist`** (Optional)
  * Regex to filter projects from `project_field`

* **`safe_instance_fields`** (Optional)
  * Comma-separated field names to sanitize for instance naming
  * Values sanitized but not used as instance name

* **`agent_http_proxy`** (Optional)
  * HTTP proxy URL
  * Example: `http://proxy.example.com:8080`

* **`agent_https_proxy`** (Optional)
  * HTTPS proxy URL

#### InsightFinder Settings

* **`user_name`** (Required)
  * Your InsightFinder username/email

* **`license_key`** (Required)
  * License key from your InsightFinder account profile

* **`token`** (Optional)
  * Authentication token (alternative to license_key)

* **`project_name`** (Required)
  * Name of the project in InsightFinder
  * Will be auto-created if it doesn't exist

* **`system_name`** (Optional)
  * Name of system owning the project
  * Used when auto-creating projects

* **`project_type`** (Required)
  * Type of project
  * Values: `metric`, `metricreplay`, `log`, `logreplay`, `incident`, `incidentreplay`, `alert`, `alertreplay`, `deployment`, `deploymentreplay`
  * Most common: `log` or `metric`

* **`containerize`** (Optional)
  * Set to `YES` for container projects
  * Default: `no`

* **`enable_holistic_model`** (Optional)
  * Enable holistic model when auto-creating project
  * Default: `false`

* **`sampling_interval`** (Required)
  * Data collection frequency in minutes
  * Should match project settings
  * Default: `10`

* **`run_interval`** (Required)
  * How frequently the agent runs in minutes
  * Should match cron schedule
  * Default: `10`

* **`worker_timeout`** (Optional)
  * Worker process timeout in minutes
  * Default: same as `run_interval`

* **`frequency_sampling_interval`** (Optional)
  * Hot/cold event detection frequency in minutes
  * Default: `10`

* **`log_compression_interval`** (Optional)
  * Log compression frequency in minutes
  * Default: `1`

* **`enable_log_rotation`** (Optional)
  * Enable daily log rotation: `True` or `False`
  * Default: `False`

* **`log_backup_count`** (Optional)
  * Number of log files to retain when rotation is enabled
  * Default: `14`

* **`chunk_size_kb`** (Optional)
  * Size of data chunks sent to InsightFinder in KB
  * Default: `2048`

* **`if_url`** (Optional)
  * InsightFinder URL
  * Default: `https://app.insightfinder.com`

* **`if_http_proxy`** (Optional)
  * HTTP proxy for InsightFinder connection

* **`if_https_proxy`** (Optional)
  * HTTPS proxy for InsightFinder connection

## Troubleshooting

### Docker
```bash
# Check container status
docker ps -a | grep elasticsearch-collector

# View recent logs
docker logs --tail 100 elasticsearch-collector

# Access container shell
docker exec -it elasticsearch-collector /bin/bash

# Test configuration inside container
docker exec -it elasticsearch-collector python3 getmessages_elasticsearch_collector.py -t
```

### Local Installation
```bash
# Check if agent is running
ps aux | grep cron.py

# View recent logs
tail -100 logs/*.log

# Test configuration
./setup/test_agent.sh

# Run in foreground for debugging
venv/bin/python3 cron.py -v
```

### Common Issues

**Connection to Elasticsearch fails:**
- Verify `es_uris` is correct and accessible
- Check `http_auth` credentials are valid (and obfuscated)
- Ensure SSL settings match your Elasticsearch configuration

**No data in InsightFinder:**
- Verify `license_key` and `project_name` are correct
- Check `indeces` pattern matches your Elasticsearch indices
- Review agent logs for errors
- Ensure `timestamp_field` exists in your data

**Permission errors (Docker):**
- Ensure mounted directories have correct permissions
- Container runs as user `1001` - adjust ownership if needed:
  ```bash
  sudo chown -R 1001:1001 conf.d logs
  ```

