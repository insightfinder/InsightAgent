"""
Derived Metrics for UniFi Agent
--------------------------------
Point to this file from .env:

    DERIVED_METRICS_SCRIPT=/path/to/derived_metrics.py

Each entry in DERIVED_METRICS is a dict with:
  name           — name of the new synthetic metric sent to InsightFinder
  condition      — callable(tags, metrics) -> bool
                     tags:    dict of AP context  e.g. {'site': 'HQ', 'ap_name': 'AP-01', 'status': 'online'}
                     metrics: dict of metric name -> float for this AP at this timestamp
  value_if_true  — value to send when condition is True
  value_if_false — (optional) value to send when condition is False;
                   omit the key entirely to NOT send anything when condition is False

Available metric names (all 5 GHz):
  Channel Utilization (5GHz)         — total airtime utilization (%)
  Channel Utilization Rx (5GHz)      — receive airtime utilization (%)
  Channel Utilization Tx (5GHz)      — transmit airtime utilization (%)
  Clients (5GHz)                     — number of associated 5 GHz clients
  RSSI Average (5GHz)                — average client RSSI (absolute dBm, e.g. 72 means -72 dBm)
  SNR Average (5GHz)                 — average client SNR (dB)
  % Clients RSSI < -74 dBm (5GHz)   — % of clients with RSSI worse than -74 dBm
  % Clients RSSI < -78 dBm (5GHz)   — % of clients with RSSI worse than -78 dBm
  % Clients RSSI < -80 dBm (5GHz)   — % of clients with RSSI worse than -80 dBm
  % Clients SNR < 15 dB (5GHz)      — % of clients with SNR below 15 dB
  % Clients SNR < 18 dB (5GHz)      — % of clients with SNR below 18 dB
  % Clients SNR < 20 dB (5GHz)      — % of clients with SNR below 20 dB

Rules:
- If any metric referenced in the condition is missing the rule is silently skipped.
- Percentage metrics are 0.0 when the AP has fewer clients than MIN_CLIENTS_RSSI/SNR_THRESHOLD.
"""

DERIVED_METRICS = [
    # Poor signal coverage + high airtime congestion
    # Mirrors: >= 35% of clients RSSI < -78 dBm AND Airtime Utilization > 85%
    {
        'name': '>= 35% of clients RSSI < -78 dBm AND Channel Utilization (5GHz) > 85',
        'condition': lambda tags, metrics: (
            metrics['% Clients RSSI < -78 dBm (5GHz)'] >= 35 and
            metrics['Channel Utilization (5GHz)'] > 85
        ),
        'value_if_true': 1,
    },

    # Poor signal + poor SNR — double RF degradation
    # Mirrors: >= 35% of clients RSSI < -78 dBm AND SNR/SINR < 18 dB
    {
        'name': '>= 35% of clients RSSI < -78 dBm AND >= 35% of clients SNR < 18 dB',
        'condition': lambda tags, metrics: (
            metrics['% Clients RSSI < -78 dBm (5GHz)'] >= 35 and
            metrics['% Clients SNR < 18 dB (5GHz)'] >= 35
        ),
        'value_if_true': 1,
    },

]
