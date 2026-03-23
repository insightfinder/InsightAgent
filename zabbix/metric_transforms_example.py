"""
Example metric transform script for InsightAgent Zabbix.

Set metric_transform_script = metric_transforms_example.py in config.ini
(relative path works when the agent is run from the zabbix/ directory).

TRANSFORMS is a list of (pattern, fn) tuples evaluated top-to-bottom.
The first matching entry wins — put specific (exact) entries before
general (regex) entries.

  pattern: str          -> exact match against metric name
  pattern: re.compile() -> regex match against metric name

fn return types:
  float        -> transform value only, metric name unchanged
  (str, float) -> change metric name AND value
"""
import re

TRANSFORMS = [
    # --- Value only (name unchanged) ---

    # Exact: CPU idle has a special +5 offset for this environment
    ("CPU idle time",      lambda name, val: val * 100 + 5),

    # Exact: round memory utilisation percentage to 2 decimal places
    ("Memory utilization", lambda name, val: round(val, 2)),

    # Regex: all other CPU metrics — convert 0-1 fraction to percentage
    (re.compile(r"CPU.*"),  lambda name, val: val * 100),

    # Regex: all ICMP metrics — seconds to milliseconds
    (re.compile(r"ICMP.*"), lambda name, val: val * 1000),


    # --- Value + rename (return a tuple) ---

    # Exact: rename and convert bytes to GB
    ("Memory used",        lambda name, val: ("memory.used.gb", val / (1024 ** 3))),

    # Regex: all memory metrics — bytes to GB, normalize name to lowercase with dots
    (re.compile(r"Memory.*"), lambda name, val: (name.lower().replace(" ", "."), val / (1024 ** 3))),

    # Regex: network throughput — bytes/s to Mbps, prefix name
    (re.compile(r"(?i).*network.*bits.*"), lambda name, val: ("network.mbps." + name, val / 1_000_000)),
]
