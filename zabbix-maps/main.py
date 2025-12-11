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

# InsightFinder API credentials
INSIGHTFINDER_URL = 'https://stg.insightfinder.com/api/v2/updaterelationsdependency'  # Update with your actual URL
IF_USERNAME = 'your_username'  # Update with your InsightFinder username
IF_LICENSE_KEY = 'your_license_key'  # Update with your license key
IF_PROJECT_NAME = 'your_project_name'  # Update with your project name
IF_SYSTEM_NAME = 'systemName'  # Update with your system display name

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

# Send dependency data to InsightFinder
def send_to_insightfinder(component_relations):
    payload = {
        "systemDisplayName": IF_SYSTEM_NAME,
        "licenseKey": IF_LICENSE_KEY,
        "userName": IF_USERNAME,
        "projectName": IF_PROJECT_NAME,
        "componentRelationList": component_relations
    }
    
    print(f"\nSending {len(component_relations)} relations to InsightFinder...")
    response = requests.post(INSIGHTFINDER_URL, json=payload)
    
    if response.status_code == 200:
        print("Successfully sent data to InsightFinder!")
        print("Response:", response.json())
    else:
        print(f"Error sending data: {response.status_code}")
        print("Response:", response.text)
    
    return response

if __name__ == "__main__":
    token = get_auth_token()
    
    # Fetch all maps (no map_id specified)
    print("Fetching all available Zabbix maps...")
    maps = fetch_maps(token, map_id=None)
    
    if not maps:
        print("No maps found in Zabbix.")
        exit(1)
    
    print(f"Found {len(maps)} maps in Zabbix")
    
    # Collect all device links from all maps
    all_component_relations = []
    all_links_set = set()  # To avoid duplicates across maps
    
    for map_idx, map_data in enumerate(maps, 1):
        map_name = map_data.get('name', f'Map {map_idx}')
        map_id = map_data.get('sysmapid', 'unknown')
        
        print(f"\n{'='*60}")
        print(f"Processing Map {map_idx}/{len(maps)}: {map_name} (ID: {map_id})")
        print(f"{'='*60}")
        
        if 'links' not in map_data or 'selements' not in map_data:
            print(f"  Skipping - no links or elements found")
            continue
        
        if not map_data['links']:
            print(f"  Skipping - no links in this map")
            continue
        
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
    print(f"Summary:")
    print(f"  Total maps processed: {len(maps)}")
    print(f"  Total unique device links: {len(all_component_relations)}")
    print(f"  Saved to: {output_file}")
    print(f"{'='*60}")
    
    if not all_component_relations:
        print("\nWarning: No device links found across all maps!")
        exit(1)