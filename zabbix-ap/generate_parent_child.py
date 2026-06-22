"""
Generate parent-child instance name relationships by querying the upstream API
for each device in devicelookup.json.

Instance name format mirrors getmessages_zabbix.py:
  MAC <mac with : replaced by ->  |  SERIAL <serial>  |  JIRAKEY <object_key>
"""

import json
import os
import urllib.parse
import concurrent.futures
import threading

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEVICELOOKUP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'devicelookup.json')
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'parent_child_relationships.json')

API_BASE = 'http://54.234.90.98/devices'
API_KEY = 'accessparks-keyInsight-87654321'
API_HEADERS = {'accept': 'application/json', 'X-API-Key': API_KEY}

MAX_WORKERS = 20
REQUEST_TIMEOUT = 10

_thread_local = threading.local()


def get_session():
    if not hasattr(_thread_local, 'session'):
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        session.mount('http://', HTTPAdapter(max_retries=retry))
        session.mount('https://', HTTPAdapter(max_retries=retry))
        _thread_local.session = session
    return _thread_local.session


def make_instance_name(mac_address, serial_number, object_key):
    """Mirror the effective_in logic in getmessages_zabbix.py."""
    if mac_address:
        candidate = mac_address.replace(':', '-').strip('-').strip()
        if candidate:
            return 'MAC ' + candidate
    if serial_number:
        return 'SERIAL ' + serial_number
    if object_key:
        return 'JIRAKEY ' + object_key
    return None


def query_upstream(query_identifier):
    """Call the upstream API. Returns list of parent dicts, [] if no parent, None on error/not found."""
    encoded = urllib.parse.quote(query_identifier, safe='')
    url = '{}/{}/upstream?max_depth=1'.format(API_BASE, encoded)
    try:
        resp = get_session().get(url, headers=API_HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        # {"detail": "Device not found: ..."} shape
        return None
    except Exception:
        return None


def process_entry(args):
    key, entry, idx, total = args
    if not isinstance(entry, dict):
        return None

    dev = entry.get('device', {})
    mac = (dev.get('mac_address') or '').strip()
    serial = (dev.get('serial_number') or '').strip()
    obj_key = (dev.get('object_key') or '').strip()

    child_in = make_instance_name(mac or None, serial or None, obj_key or None)
    if not child_in:
        return None

    # Use the raw (original) identifier for the URL — same priority order
    query_id = mac or serial or obj_key
    if not query_id:
        return None

    parents = query_upstream(query_id)
    if not parents:
        return None

    results = []
    for parent in parents:
        parent_in = make_instance_name(
            parent.get('mac_address') or None,
            parent.get('serial_number') or None,
            parent.get('object_key') or None,
        )
        if parent_in:
            meta_raw = parent.get('meta') or '{}'
            try:
                meta = json.loads(meta_raw)
            except (ValueError, TypeError):
                meta = {}
            zone = meta.get('venue') or None
            results.append({'child': child_in, 'parent': parent_in, 'zone': zone})

    return results or None


def main():
    with open(DEVICELOOKUP_PATH) as f:
        raw = json.load(f)

    entries = [
        (k, v, i, 0)
        for i, (k, v) in enumerate(raw.items())
        if k != 'lastmodifiedtimedata' and isinstance(v, dict)
    ]
    total = len(entries)
    # inject total now that we know it
    entries = [(k, v, i, total) for i, (k, v, _, _) in enumerate(entries)]

    print('Processing {} entries with {} workers...'.format(total, MAX_WORKERS))

    relationships = []
    lock = threading.Lock()
    done_count = [0]

    def wrapped(args):
        result = process_entry(args)
        with lock:
            done_count[0] += 1
            if done_count[0] % 500 == 0:
                print('  {}/{} processed, {} relationships so far'.format(
                    done_count[0], total, len(relationships)))
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for result in executor.map(wrapped, entries):
            if result:
                with lock:
                    relationships.extend(result)

    with open(OUTPUT_PATH, 'w') as f:
        json.dump(relationships, f, indent=2)

    print('Done. {} parent-child relationships written to {}'.format(len(relationships), OUTPUT_PATH))


if __name__ == '__main__':
    main()
