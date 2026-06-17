"""
Derived Metrics Script
----------------------
Point to this file from config.ini:

    [zabbix]
    derived_metrics_script = /path/to/derived_metrics_example.py

Each entry in DERIVED_METRICS is a dict with:
  name           — name of the new synthetic metric to send to InsightFinder
  condition      — callable(tags, metrics) -> bool
                     tags:    dict of Zabbix host tags  e.g. {'jira_make': 'Cambium', ...}
                     metrics: dict of metric name -> str value for this instance/timestamp
  value_if_true  — value to send when condition is True
  value_if_false — (optional) value to send when condition is False;
                   omit the key entirely to NOT send anything when condition is False

Rules:
- If any metric referenced in the condition is missing the rule is silently skipped.
- Metric names must match exactly what Zabbix returns after make_safe_data_key transforms:
    [ -> (    ] -> )    . -> /    _ -> -    : -> -    , -> -
- Tag names are raw Zabbix host tag names.
"""

DERIVED_METRICS = [
    # Cambium: >= 10 clients on 5GHz AND channel utilization over 85%
    # Sends highChannelUtil=1 when true, nothing when false.
    {
        'name': 'Clients (5GHz) >= 10 AND Channel utilization (5GHz) > 85',
        'condition': lambda tags, metrics: (
            tags.get('jira_make') == 'Cambium' and
            float(metrics['Clients (5GHz)']) >= 10 and
            float(metrics['Channel utilization (5GHz)']) > 85
        ),
        'value_if_true': 1,
    },

    # Cambium: >= 10 clients on 5GHz AND noise floor worse than -85 dBm (greater than -85)
    # Sends highNoise=1 when true, nothing when false.
    {
        'name': 'Clients (5GHz) >= 10 AND Noise floor (5GHz) > -85',
        'condition': lambda tags, metrics: (
            tags.get('jira_make') == 'Cambium' and
            float(metrics['Clients (5GHz)']) >= 10 and
            float(metrics['Noise floor (5GHz)']) > -85
        ),
        'value_if_true': 1,
    },
]
