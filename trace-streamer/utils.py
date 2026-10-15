import calendar
import json
from datetime import datetime


def group_by(items, key_func):
    groups = {}
    for item in items:
        groups.setdefault(key_func(item), []).append(item)
    return groups


def coerce_int_fields(mapping, keys):
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str):
            try:
                mapping[key] = int(value)
            except ValueError:
                pass
    return mapping


def parse_json_field(value):
    if not value:
        return {}
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def parse_timestamp_unix_nano(value):
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)

    text = value.strip()
    if text.endswith("UTC"):
        text = text[: -len("UTC")].strip()

    dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%f")
    return calendar.timegm(dt.timetuple()) * 1_000_000_000 + dt.microsecond * 1_000
