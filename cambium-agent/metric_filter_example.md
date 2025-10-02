# Example metric filtering configuration

# To enable only specific metrics, update the config.yaml file:

metric_filter:
  # System metrics
  available_memory: true     # Enable streaming Available Memory
  cpu_utilization: false    # Disable streaming CPU Utilization
  
  # Radio metrics
  num_clients_5g: true       # Enable streaming Num Clients 5G
  channel_utilization_5g: false
  num_clients_6g: true       # Enable streaming Num Clients 6G  
  channel_utilization_6g: false
  
  # Client-derived metrics (requires Wi-Fi devices with client data)
  rssi_avg: true            # Enable streaming RSSI Avg
  snr_avg: true             # Enable streaming SNR Avg
  clients_rssi_below_74: false
  clients_rssi_below_78: false  
  clients_rssi_below_80: false
  clients_snr_below_15: false
  clients_snr_below_18: false
  clients_snr_below_20: false

# With this configuration, only the following metrics will be streamed to InsightFinder:
# - Available Memory
# - Num Clients 5G
# - Num Clients 6G
# - RSSI Avg (if Wi-Fi device with clients)
# - SNR Avg (if Wi-Fi device with clients)
#
# All other metrics will be skipped and not sent to InsightFinder.