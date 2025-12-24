#!/usr/bin/env python3
"""
Script to extract unique zones from InsightFinder project instances
and match them with Zabbix map names
"""

import json
import logging
import sys
import re
import requests
import zone_config
import config

# Output configuration
LOG_LEVEL = logging.INFO


def setup_logging():
    """Setup basic logging"""
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def login(session: requests.Session):
    """Login to InsightFinder and retrieve authentication token"""
    login_url = f"{zone_config.insightfinder_url}/api/v1/login-check"
    login_params = {
        "userName": zone_config.insightfinder_username,
        "password": zone_config.insightfinder_password
    }

    login_response = session.post(
        login_url,
        params=login_params,
        headers={
            "User-Agent": zone_config.user_agent,
            "Content-Type": "application/json"
        }
    )

    if login_response.status_code != 200:
        print("Login failed:", login_response.text)
        exit(1)

    login_data = login_response.json()
    if not login_data.get("valid", False):
        print("Invalid login credentials.")
        exit(1)

    csrf_token = login_data.get("token", "")
    return csrf_token


def get_grouping_storage_data(session: requests.Session, token: str, project_name: str):
    """Fetch grouping storage data from InsightFinder API"""
    url = f"{zone_config.insightfinder_url}/api/v1/groupingstorage"
    
    # Based on the screenshot, the API uses POST with form data
    params = {
        'tzOffset': zone_config.tz_offset
    }
    
    form_data = {
        'projectName': project_name,
        'instanceGroup': 'All'
    }

    headers = {
        "User-Agent": zone_config.user_agent,
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "X-CSRF-TOKEN": token,
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9"
    }

    # Print debug information
    print(f"\n=== API Request Details ===")
    print(f"URL: {url}")
    print(f"Method: POST")
    print(f"Query Params: {params}")
    print(f"Form Data: {form_data}")
    print(f"Headers: {headers}")
    print(f"=========================\n")

    response = session.post(
        url,
        data=form_data,
        params=params,
        headers=headers
    )
    
    if response.status_code != 200:
        print(f"Failed to fetch grouping storage data. Status: {response.status_code}")
        print(f"Response: {response.text}")
        exit(1)
    
    response_json = response.json()
    return response_json


def extract_unique_zones(grouping_data, logger):
    """
    Extract unique zones from the grouping storage data
    
    Args:
        grouping_data: Response from the grouping/storage API
        logger: Logger object
    
    Returns:
        List of unique zone names
    """
    unique_zones = set()
    instance_zone_map = {}
    
    try:
        # Check if 'zoneData' exists at the root level
        if 'zoneData' in grouping_data and isinstance(grouping_data['zoneData'], dict):
            zone_data = grouping_data['zoneData']
            
            # Iterate through all instance-zone mappings
            for instance_name, zone in zone_data.items():
                if zone and zone.strip():  # Only include non-empty zones
                    unique_zones.add(zone)
                    instance_zone_map[instance_name] = zone
        
        logger.info(f"Found {len(unique_zones)} unique zones")
        logger.info(f"Mapped {len(instance_zone_map)} instances to zones")
        
        return sorted(list(unique_zones)), instance_zone_map
        
    except Exception as e:
        logger.error(f"Error extracting zones: {e}")
        logger.error(f"Exception details: {str(e)}")
        return [], {}


def save_zone_data(unique_zones, logger):
    """Save zone data to JSON file"""
    
    # Save unique zones list
    zones_file = "unique_zones.json"
    try:
        with open(zones_file, 'w') as f:
            json.dump({
                "zones": unique_zones,
                "total_zones": len(unique_zones)
            }, f, indent=2)
        logger.info(f"Unique zones saved to {zones_file}")
        return zones_file
    except Exception as e:
        logger.error(f"Failed to save unique zones: {e}")
        return None


def login_zabbix(session: requests.Session):
    """Login to Zabbix and get authentication token"""
    login_url = f"{config.zabbix_url}/api_jsonrpc.php"
    
    payload = {
        "jsonrpc": "2.0",
        "method": "user.login",
        "params": {
            "username": config.zabbix_user,
            "password": config.zabbix_password
        },
        "id": 1
    }
    
    headers = {
        "Content-Type": "application/json-rpc"
    }
    
    response = session.post(login_url, json=payload, headers=headers)
    
    if response.status_code != 200:
        print(f"Zabbix login failed. Status: {response.status_code}")
        return None
    
    result = response.json()
    if 'result' not in result:
        print(f"Zabbix login failed: {result.get('error', 'Unknown error')}")
        return None
    
    return result['result']


def fetch_zabbix_maps(session: requests.Session, auth_token: str):
    """Fetch all maps from Zabbix"""
    api_url = f"{config.zabbix_url}/api_jsonrpc.php"
    
    payload = {
        "jsonrpc": "2.0",
        "method": "map.get",
        "params": {
            "output": ["sysmapid", "name"]
        },
        "auth": auth_token,
        "id": 2
    }
    
    headers = {
        "Content-Type": "application/json-rpc"
    }
    
    response = session.post(api_url, json=payload, headers=headers)
    
    if response.status_code != 200:
        print(f"Failed to fetch Zabbix maps. Status: {response.status_code}")
        return []
    
    result = response.json()
    if 'result' not in result:
        print(f"Failed to fetch maps: {result.get('error', 'Unknown error')}")
        return []
    
    return result['result']


def sanitize_map_name(map_name: str) -> str:
    """
    Remove text in parentheses from map name.
    Example: "Adventure Bound (Network Map)" -> "Adventure Bound"
    """
    # Remove anything in parentheses and trim whitespace
    sanitized = re.sub(r'\s*\([^)]*\)\s*', '', map_name).strip()
    return sanitized


def match_maps_to_zones(maps, zones, logger):
    """
    Match Zabbix map names (after sanitization) to InsightFinder zones.
    
    Returns:
        dict: Contains matched and unmatched maps
    """
    matched = []
    unmatched = []
    
    # Create a set of zones for faster lookup
    zone_set = set(zones)
    
    for map_item in maps:
        map_id = map_item.get('sysmapid')
        original_name = map_item.get('name', '')
        sanitized_name = sanitize_map_name(original_name)
        
        match_info = {
            "map_id": map_id,
            "original_name": original_name,
            "sanitized_name": sanitized_name
        }
        
        if sanitized_name in zone_set:
            match_info["matched_zone"] = sanitized_name
            matched.append(match_info)
        else:
            unmatched.append(match_info)
    
    logger.info(f"Matched {len(matched)} maps to zones")
    logger.info(f"Found {len(unmatched)} maps without matching zones")
    
    return {
        "matched": matched,
        "unmatched": unmatched,
        "total_maps": len(maps),
        "total_matched": len(matched),
        "total_unmatched": len(unmatched)
    }


def save_map_zone_matching(matching_results, filename="map_zone_matching.json"):
    """Save the map-zone matching results to a JSON file"""
    try:
        with open(filename, 'w') as f:
            json.dump(matching_results, f, indent=2)
        print(f"Map-zone matching saved to {filename}")
        return True
    except Exception as e:
        print(f"Failed to save matching results: {e}")
        return False


def main():
    """Main function"""
    logger = setup_logging()
    
    project_name = zone_config.insightfinder_project
    
    if not project_name:
        logger.error("Project name not configured in zone_config.py")
        sys.exit(1)
    
    # Step 1: Login to InsightFinder
    logger.info("Logging in to InsightFinder...")
    session = requests.Session()
    token = login(session)
    logger.info("Successfully logged in")
    
    # Step 2: Fetch grouping storage data
    logger.info(f"Fetching grouping storage data for project: {project_name}")
    grouping_data = get_grouping_storage_data(session, token, project_name)
    
    # Save raw response for debugging
    logger.info("Saving raw API response for inspection...")
    try:
        with open("raw_grouping_response.json", 'w') as f:
            json.dump(grouping_data, f, indent=2)
        logger.info("Raw response saved to raw_grouping_response.json")
    except Exception as e:
        logger.error(f"Failed to save raw response: {e}")
    
    # Step 3: Extract unique zones
    logger.info("Extracting unique zones...")
    unique_zones, instance_zone_map = extract_unique_zones(grouping_data, logger)
    
    if not unique_zones:
        logger.warning("No zones found in the response")
    else:
        logger.info(f"\nUnique Zones Found ({len(unique_zones)}):")
        for i, zone in enumerate(unique_zones, 1):
            logger.info(f"  {i}. {zone}")
    
    # Step 4: Save results to file
    logger.info("\nSaving results to file...")
    zones_file = save_zone_data(unique_zones, logger)
    
    if zones_file:
        logger.info(f"Results saved to: {zones_file}")
    else:
        logger.error("Failed to save zone data")
        sys.exit(1)
    
    # Step 5: Login to Zabbix
    logger.info("\nLogging in to Zabbix...")
    zabbix_session = requests.Session()
    zabbix_token = login_zabbix(zabbix_session)
    
    if not zabbix_token:
        logger.error("Failed to login to Zabbix")
        sys.exit(1)
    
    logger.info("Successfully logged in to Zabbix")
    
    # Step 6: Fetch Zabbix maps
    logger.info("Fetching Zabbix maps...")
    maps = fetch_zabbix_maps(zabbix_session, zabbix_token)
    logger.info(f"Found {len(maps)} Zabbix maps")
    
    if not maps:
        logger.warning("No maps found in Zabbix")
        sys.exit(0)
    
    # Step 7: Match maps to zones
    logger.info("\nMatching Zabbix maps to InsightFinder zones...")
    matching_results = match_maps_to_zones(maps, unique_zones, logger)
    
    # Step 8: Save matching results
    logger.info("\nSaving map-zone matching results...")
    if save_map_zone_matching(matching_results):
        logger.info("\nProcess completed successfully!")
        logger.info(f"\nSummary:")
        logger.info(f"  - Total zones: {len(unique_zones)}")
        logger.info(f"  - Total maps: {matching_results['total_maps']}")
        logger.info(f"  - Matched maps: {matching_results['total_matched']}")
        logger.info(f"  - Unmatched maps: {matching_results['total_unmatched']}")
        logger.info(f"\nOutput files:")
        logger.info(f"  - {zones_file}")
        logger.info(f"  - map_zone_matching.json")
    else:
        logger.error("Failed to save matching results")


if __name__ == "__main__":
    main()
