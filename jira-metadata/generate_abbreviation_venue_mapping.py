#!/usr/bin/env python3

import configparser
import requests
import yaml

def get_all_objects(username, api_token, workspace_id, object_type):
    """Fetches all objects of a given type from Jira Assets."""
    endpoint = f"https://api.atlassian.com/jsm/assets/workspace/{workspace_id}/v1/aql/objects"
    all_objects = []
    page = 1

    print(f"Fetching {object_type} objects...")
    while True:
        params = {
            "qlQuery": f'objectType = "{object_type}"',
            "page": page,
            "resultsPerPage": 25,
            "includeAttributes": "true",
            "includeTypeAttributes": "true"
        }
        
        response = requests.get(endpoint, params=params, auth=(username, api_token), timeout=60)
        response.raise_for_status()
        
        objects = response.json().get("objectEntries", [])
        all_objects.extend(objects)
        
        if len(objects) < 25:
            break
        page += 1
    
    return all_objects

def get_abbreviation_key(venue):
    """Returns the abbreviation objectKey linked to this venue, or None."""
    for attr in venue.get("attributes", []):
        for val in attr.get("objectAttributeValues", []):
            ref = val.get("referencedObject", {})
            if ref.get("objectType", {}).get("name", "").lower() == "abbreviation":
                return ref.get("objectKey")
    return None

def main():
    config = configparser.ConfigParser()
    config.read("conf.d/config.ini")
    
    username = config.get("Jira", "username")
    api_token = config.get("Jira", "api_token")
    workspace_id = config.get("Jira", "workspace_id")

    # Fetch data
    abbreviations = get_all_objects(username, api_token, workspace_id, "abbreviation")
    venues = get_all_objects(username, api_token, workspace_id, "venue")
    
    print(f"Found {len(abbreviations)} abbreviations and {len(venues)} venues.")
    
    # Build lookup and mapping
    abbr_lookup = {abbr["objectKey"]: abbr["label"] for abbr in abbreviations}
    zone_mapping = {}
    unmapped_venues = []
    
    for venue in venues:
        abbr_key = get_abbreviation_key(venue)
        if abbr_key and abbr_key in abbr_lookup:
            abbr_name = abbr_lookup[abbr_key]
            if abbr_name not in zone_mapping:
                zone_mapping[abbr_name] = venue["label"]
                print(f"Mapped: {abbr_name} -> {venue['label']}")
        else:
            unmapped_venues.append(venue["label"])
    
    if not zone_mapping:
        print("ERROR: No mappings found. Venues may not be linked to abbreviations in Jira.")
        return
    
    # Write output
    with open("zone_mapping.yaml", 'w') as f:
        yaml.dump(zone_mapping, f, default_flow_style=False, sort_keys=True)
    
    print(f"\n✓ Created zone_mapping.yaml with {len(zone_mapping)} mappings.")
    
    if unmapped_venues:
        print(f"\n⚠ {len(unmapped_venues)} venues could not be mapped (no abbreviation link):")
        for venue_name in unmapped_venues:
            print(f"  - {venue_name}")

if __name__ == "__main__":
    main()
