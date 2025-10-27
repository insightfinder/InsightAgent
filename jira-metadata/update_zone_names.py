import configparser
import yaml
import json
import requests
import sys

CONFIG_FILE = "conf.d/config.ini"
METADATA_FILE = "instance_metadata.yaml"
ZONE_MAPPING_FILE = "zone_mapping.yaml"

def load_zone_mapping():
    """Load zone mapping from YAML file."""
    try:
        with open(ZONE_MAPPING_FILE, 'r') as f:
            zone_mapping = yaml.safe_load(f)
        print(f"Loaded zone mapping with {len(zone_mapping)} entries from {ZONE_MAPPING_FILE}")
        return zone_mapping if zone_mapping else {}
    except FileNotFoundError:
        print(f"Warning: {ZONE_MAPPING_FILE} not found. Fallback mapping will not be available.")
        return {}
    except Exception as e:
        print(f"Error loading {ZONE_MAPPING_FILE}: {e}")
        return {}

def extract_prefix(instance_name, zone_mapping):
    """
    Extract the prefix from instance name and find matching zone.
    First tries splitting by '-', then by '.' if no match found.
    Returns (prefix, zone_name) tuple or (prefix, None) if no match.
    """
    # Try splitting by hyphen first
    if '-' in instance_name:
        prefix = instance_name.split('-')[0].lower()
        zone_name = zone_mapping.get(prefix)
        if zone_name:
            return (prefix, zone_name)
    
    # If no match with hyphen, try splitting by period
    if '.' in instance_name:
        prefix = instance_name.split('.')[0].lower()
        zone_name = zone_mapping.get(prefix)
        if zone_name:
            return (prefix, zone_name)
    
    return ("", None)

def update_zone_names():
    """
    Updates zone names for instances in an InsightFinder project
    by reading venue_name from instance metadata and sending to the API.
    If venue_name is not found, uses zone mapping based on prefix.
    """
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    with open(METADATA_FILE, 'r') as f:
        metadata = yaml.safe_load(f)

    # Load zone mapping for fallback
    zone_mapping = load_zone_mapping()

    # InsightFinder config
    if_config = config['InsightFinder']
    if_url = if_config['insightfinder_url']
    username = if_config['username']
    license_key = if_config['license_key']

    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <project_name>")
        sys.exit(1)
    project = sys.argv[1]

    payload = []
    fallback_count = 0
    skipped_count = 0
    
    for instance_name, instance_data in metadata.items():

        zone_name = None
        venue_name = instance_data.get('venue_name')
        
        if venue_name:
            # Primary: Use venue_name from metadata
            zone_name = venue_name
        else:
            # Fallback: Extract prefix and look up in zone mapping
            prefix, zone_name = extract_prefix(instance_name, zone_mapping)
            if zone_name:
                fallback_count += 1
                print(f"Using fallback zone mapping for '{instance_name}': prefix '{prefix}' -> zone '{zone_name}'")
            else:
                print(f"Warning: No venue_name or zone mapping found for instance '{instance_name}' (prefix: '{prefix}')")
                skipped_count += 1
        
        if zone_name:
            instance_payload = {
                "instanceName": instance_name,
                "zone": zone_name
            }
            payload.append(instance_payload)

    # Prepare for InsightFinder API call
    endpoint = f"{if_url}/api/v1/agent-upload-instancemetadata"
    params = {
        "userName": username,
        "licenseKey": license_key,
        "projectName": project,
        "override": "true"
    }

    if not payload:
        print(f"No valid zone names to update for project {project}")
        return
    
    print(f"Prepared {len(payload)} zone name updates ({fallback_count} using fallback mapping). Skipped {skipped_count} instances without zone names.")
    
    try:
        response = requests.post(endpoint, json=payload, params=params)
        response.raise_for_status()  # Raise an exception for bad status codes
        print("Zone names successfully updated in InsightFinder.")
        print(f"Response: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error updating zone names in InsightFinder: {e}")

if __name__ == "__main__":
    update_zone_names()
