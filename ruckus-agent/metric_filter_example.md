# Ruckus Agent Metric Filtering Example

# To enable only specific metrics, update the config.yaml file:

metric_filter:
  # Client count metrics
  num_clients_total: true      # Enable streaming Num Clients Total
  num_clients_24g: false       # Disable streaming Num Clients 24G
  num_clients_5g: true         # Enable streaming Num Clients 5G
  num_clients_6g: true         # Enable streaming Num Clients 6G
  
  # Airtime metrics (channel utilization percentages)
  airtime_24g: false          # Disable streaming Airtime 24G Percent
  airtime_5g: true            # Enable streaming Airtime 5G Percent
  airtime_6g: false           # Disable streaming Airtime 6G Percent
  
  # Client-derived metrics (requires client data enrichment)
  rssi_avg: true              # Enable streaming RSSI Avg
  snr_avg: true               # Enable streaming SNR Avg
  clients_rssi_below_74: false
  clients_rssi_below_78: true  # Enable streaming % Clients RSSI < -78 dBm
  clients_rssi_below_80: false
  clients_snr_below_15: false
  clients_snr_below_18: false
  clients_snr_below_20: true   # Enable streaming % Clients SNR < 20 dBm
  
  # Ethernet metrics
  ethernet_status_mbps: true   # Enable streaming Ethernet Status Mbps

# With this configuration, only the following metrics will be streamed to InsightFinder:
# - Num Clients Total
# - Num Clients 5G
# - Num Clients 6G
# - Airtime 5G Percent
# - RSSI Avg (if client data is available)
# - SNR Avg (if client data is available)
# - % Clients RSSI < -78 dBm (if client data is available)
# - % Clients SNR < 20 dBm (if client data is available)
# - Ethernet Status Mbps (extracted from poePortStatus, e.g., "100Mbps" -> 100)
#
# All other metrics will be skipped and not sent to InsightFinder.

# Benefits:
# 1. Reduced bandwidth usage
# 2. Lower InsightFinder ingestion costs
# 3. Focused monitoring on key metrics
# 4. Customizable per deployment requirements