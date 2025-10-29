import configparser
import yaml
import json
import re
import requests
import sys

CONFIG_FILE = "conf.d/config.ini"
METADATA_FILE = "instance_metadata.yaml"
ZONE_MAPPING_FILE = "zone_mapping.yaml"

def load_zone_mapping():
    """Load zone mapping from YAML file for fallback."""
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

def get_venue_id_from_zone_mapping(instance_name, zone_mapping):
    """
    Extract the prefix from instance name and find matching venue_id from zone_mapping.
    First tries splitting by '-', then by '.' if no match found.
    Returns venue_id if found, None otherwise.
    """
    # Try splitting by hyphen first
    if '-' in instance_name:
        prefix = instance_name.split('-')[0].lower()
        zone_entry = zone_mapping.get(prefix)
        if zone_entry:
            # Handle nested structure (venue_name/venue_id)
            if isinstance(zone_entry, dict):
                venue_id = zone_entry.get("venue_id")
                if venue_id:
                    print(f"Fallback: Using zone mapping for '{instance_name}': prefix '{prefix}' -> venue_id '{venue_id}'")
                    return venue_id
    
    # If no match with hyphen, try splitting by period
    if '.' in instance_name:
        prefix = instance_name.split('.')[0].lower()
        zone_entry = zone_mapping.get(prefix)
        if zone_entry:
            # Handle nested structure (venue_name/venue_id)
            if isinstance(zone_entry, dict):
                venue_id = zone_entry.get("venue_id")
                if venue_id:
                    print(f"Fallback: Using zone mapping for '{instance_name}': prefix '{prefix}' -> venue_id '{venue_id}'")
                    return venue_id
    
    print(f"Warning: No venue_id found in zone mapping for instance '{instance_name}'")
    return None

def generate_payload():
    """
    Generates a JSON payload based on instance metadata and JIRA field mappings,
    and sends it to the InsightFinder API.
    """
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    with open(METADATA_FILE, 'r') as f:
        metadata = yaml.safe_load(f)

    # Load zone mapping for fallback
    zone_mapping = load_zone_mapping()

    field_mapping = config['Jira_Field_Mapping']
    workspace_id = config['Jira']['workspace_id']

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
        jira_issue_fields = {}
        used_fallback = False
        
        if "error" in instance_data:
            # Fallback: Try to get venue_id from zone_mapping
            venue_id = get_venue_id_from_zone_mapping(instance_name, zone_mapping)
            if venue_id:
                # Only add venue_id field mapping if found
                venue_id_field = None
                for custom_field, yaml_key in field_mapping.items():
                    if yaml_key == "venue_id":
                        venue_id_field = custom_field
                        break
                
                if venue_id_field:
                    jira_issue_fields[venue_id_field] = f"{workspace_id}:{venue_id}"
                    used_fallback = True
                    fallback_count += 1
                else:
                    print(f"Warning: No venue_id field mapping found in config for '{instance_name}'")
                    skipped_count += 1
                    continue
            else:
                print(f"Skipping instance '{instance_name}': error in metadata and no fallback available")
                skipped_count += 1
                continue
        else:
            # Normal processing: use metadata
            for custom_field, yaml_key in field_mapping.items():
                if yaml_key in instance_data:
                    yaml_value = str(instance_data[yaml_key])
                    sanitized_value = re.sub(r'\D', '', yaml_value)
                    jira_issue_fields[custom_field] = f"{workspace_id}:{sanitized_value}"

        if jira_issue_fields:
            instance_payload = {
                "instanceName": instance_name,
                "jiraConfigs": {
                    "jiraIssueFields": jira_issue_fields
                }
            }
            payload.append(instance_payload)

    # Prepare for InsightFinder API call
    endpoint = f"{if_url}/api/v1/agent-upload-third-party-instancemetadata"
    params = {
        "customerName": username,
        "licenseKey": license_key,
        "projectName": project
    }

    if not payload:
        print(f"No valid metadata to send for project {project}")
        return
    
    print(f"Prepared {len(payload)} instances to send ({fallback_count} using fallback mapping). Skipped {skipped_count} instances.")
    
    try:
        response = requests.post(endpoint, json=payload, params=params)
        response.raise_for_status()  # Raise an exception for bad status codes
        print("Payload successfully sent to InsightFinder.")
        print(f"Response: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending payload to InsightFinder: {e}")

if __name__ == "__main__":
    generate_payload()