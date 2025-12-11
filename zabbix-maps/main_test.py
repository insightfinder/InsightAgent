import requests
import json
import re

# Regular expressions for safe string conversion
UNDERSCORE = re.compile(r"\_+")
COLONS = re.compile(r"\:+")
LEFT_BRACE = re.compile(r"\[")
RIGHT_BRACE = re.compile(r"\]")
PERIOD = re.compile(r"\.")
COMMA = re.compile(r"\,")

# Zabbix server and credentials
ZABBIX_URL = 'http://localhost:9999/zabbix/api_jsonrpc.php'
USERNAME = 'insight.finder'
PASSWORD = '2ri2T*%HKxbs'

# Testing configuration - limit to first 5 maps with data
MAX_MAPS_TO_PROCESS = 5

# Authenticate and get API token
def get_auth_token():
    payload = {
        "jsonrpc": "2.0",
        "method": "user.login",
        "params": {
            "user": USERNAME,
            "password": PASSWORD
        },
        "id": 1
    }
    response = requests.post(ZABBIX_URL, json=payload)
    return response.json()['result']

# Fetch maps
def fetch_maps(auth_token, map_id=None):
    params = {
        "output": "extend",
        "selectSelements": "extend",
        "selectLinks": "extend"
    }
    if map_id:
        params["sysmapids"] = [str(map_id)]
    payload = {
        "jsonrpc": "2.0",
        "method": "map.get",
        "params": params,
        "auth": auth_token,
        "id": 2
    }
    response = requests.post(ZABBIX_URL, json=payload)
    resp_json = response.json()
    if 'result' in resp_json:
        return resp_json['result']
    else:
        print('Error in response:', json.dumps(resp_json, indent=2))
        raise Exception(f"Zabbix API error: {resp_json.get('error', 'Unknown error')}")

# Fetch host information
def fetch_host(auth_token, host_id):
    payload = {
        "jsonrpc": "2.0",
        "method": "host.get",
        "params": {
            "output": ["hostid", "host", "name"],
            "hostids": [str(host_id)]
        },
        "auth": auth_token,
        "id": 3
    }
    response = requests.post(ZABBIX_URL, json=payload)
    resp_json = response.json()
    if 'result' in resp_json and resp_json['result']:
        return resp_json['result'][0]
    return None

def make_safe_instance_string(instance, device=''):
    """ make a safe instance name string, concatenated with device if appropriate """
    # strip underscores
    instance = UNDERSCORE.sub('.', instance)
    instance = COLONS.sub('-', instance)
    
    # remove leading special characters (hyphens, underscores, etc.)
    instance = re.sub(r'^[-_\W]+', '', instance)
    
    # if there's a device, concatenate it to the instance with an underscore
    if device:
        instance = '{}_{}'.format(make_safe_instance_string(device), instance)
    return instance

if __name__ == "__main__":
    token = get_auth_token()
    
    # Fetch all maps (no map_id specified)
    print("Fetching all available Zabbix maps...")
    maps = fetch_maps(token, map_id=None)
    
    if not maps:
        print("No maps found in Zabbix.")
        exit(1)
    
    print(f"Found {len(maps)} total maps in Zabbix")
    print(f"TEST MODE: Will process only first {MAX_MAPS_TO_PROCESS} maps with data\n")
    
    # Collect all device links from all maps
    all_component_relations = []
    all_links_set = set()  # To avoid duplicates across maps
    maps_processed = 0
    
    for map_idx, map_data in enumerate(maps, 1):
        # Stop after processing MAX_MAPS_TO_PROCESS maps with data
        if maps_processed >= MAX_MAPS_TO_PROCESS:
            print(f"\nReached limit of {MAX_MAPS_TO_PROCESS} maps with data. Stopping.")
            break
        
        map_name = map_data.get('name', f'Map {map_idx}')
        map_id = map_data.get('sysmapid', 'unknown')
        
        print(f"\n{'='*60}")
        print(f"Checking Map {map_idx}/{len(maps)}: {map_name} (ID: {map_id})")
        print(f"{'='*60}")
        
        if 'links' not in map_data or 'selements' not in map_data:
            print(f"  Skipping - no links or elements found")
            continue
        
        if not map_data['links']:
            print(f"  Skipping - no links in this map")
            continue
        
        # This map has data, count it
        maps_processed += 1
        print(f"  Processing map {maps_processed}/{MAX_MAPS_TO_PROCESS} with data...")
        
        # Build mapping from selementid to device name for this map
        selement_name_map = {}
        for selement in map_data['selements']:
            # elementtype 0 = host, 1 = map, 2 = trigger, 3 = host group, 4 = image
            if selement['elementtype'] == '0':  # Host
                host = fetch_host(token, selement['elements'][0]['hostid'])
                if host:
                    selement_name_map[selement['selementid']] = host.get('name', host.get('host', 'Unknown'))
                else:
                    selement_name_map[selement['selementid']] = f"Host ID:{selement['elements'][0]['hostid']}"
            else:
                selement_name_map[selement['selementid']] = selement.get('label', f"ID:{selement['selementid']}")
        
        # Process links for this map
        map_links_count = 0
        print(f"  Processing {len(map_data['links'])} links...")
        
        for link in map_data['links']:
            name1 = selement_name_map.get(link['selementid1'], link['selementid1'])
            name2 = selement_name_map.get(link['selementid2'], link['selementid2'])
            
            # Make names safe for InsightFinder
            safe_name1 = make_safe_instance_string(name1)
            safe_name2 = make_safe_instance_string(name2)
            
            # Create a tuple for deduplication
            link_tuple = (safe_name1, safe_name2)
            
            # Only add if not already added from another map
            if link_tuple not in all_links_set:
                all_links_set.add(link_tuple)
                all_component_relations.append({
                    "s": safe_name1,
                    "t": safe_name2
                })
                map_links_count += 1
                print(f"    Link: {safe_name1} -> {safe_name2}")
        
        print(f"  Added {map_links_count} unique links from this map")
    
    # Save all device links to JSON file
    output_file = 'device_links.json'
    with open(output_file, 'w') as f:
        json.dump(all_component_relations, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"TEST MODE Summary:")
    print(f"  Total maps in Zabbix: {len(maps)}")
    print(f"  Maps with data processed: {maps_processed}/{MAX_MAPS_TO_PROCESS}")
    print(f"  Total unique device links: {len(all_component_relations)}")
    print(f"  Saved to: {output_file}")
    print(f"{'='*60}")
    
    if not all_component_relations:
        print("\nWarning: No device links found in processed maps!")
        exit(1)
