#!/usr/bin/env python3
"""
Simple script to update InsightFinder component names based on instance names
"""

import json
import logging
import sys
import requests
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
    login_url = f"{config.insightfinder_url}/api/v1/login-check"
    login_params = {
        "userName": config.insightfinder_username,
        "password": config.insightfinder_password
    }

    login_response = session.post(
        login_url,
        params=login_params,
        headers={
            "User-Agent": config.user_agent,
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


def get_project_metadata(session: requests.Session, token: str, project_name: str):
    """Fetch project metadata including instances"""
    project_list = [{
        "projectName": project_name,
        "customerName": config.insightfinder_username
    }]
    
    form_data = {
        "projectList": json.dumps(project_list),
        "includeInstance": True
    }

    metadata_response = session.post(
        f"{config.insightfinder_url}/api/v1/loadProjectsMetaDataInfo",
        data=form_data,
        params={'tzOffset': -18000000},
        headers={
            "User-Agent": config.user_agent,
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "X-CSRF-TOKEN": token
        }
    )
    
    response_json = metadata_response.json()
    return response_json


def extract_instances_from_metadata(project_metadata, logger):
    """Extract instance list from project metadata"""
    instances = []
    
    if 'data' not in project_metadata or len(project_metadata['data']) == 0:
        logger.error("No project data found")
        return instances
    
    if 'instanceStructureSet' not in project_metadata['data'][0]:
        logger.error("instanceStructureSet not found in project metadata")
        return instances
    
    instances_dict = project_metadata['data'][0]['instanceStructureSet']
    
    for entry in instances_dict:
        if 'i' not in entry or entry['i'].strip() == "":
            continue
        
        instance_name = entry['i']
        instances.append(instance_name)
        
        # Handle containers if they exist
        if 'c' in entry and entry['c'] is not None:
            container_list = entry['c']
            for container in container_list:
                instances.append(f"{container}_{instance_name}")
    
    return instances


def extract_component_names(instances, logger):
    """
    Extract component names from instance names based on hyphen pattern.
    Handles both formats:
    - With spaces: 'a - b - c' -> 'a - b', 'a - b' -> 'a'
    - Without spaces: 'a-b-c' -> 'a-b', 'a-b' -> 'a'
    Preserves internal spaces, trims leading/trailing spaces only.
    
    Args:
        instances: List of instance names
        logger: Logger object
    
    Returns:
        Dictionary mapping instance names to component names
    """
    instance_component_map = {}
    skipped_count = 0
    
    for instance in instances:
        # Try splitting by ' - ' (space-hyphen-space) first
        parts_with_spaces = instance.split(' - ')
        
        if len(parts_with_spaces) >= 3:
            # Format: 'a - b - c' -> component: 'a - b'
            component_name = ' - '.join(parts_with_spaces[:2]).strip()
            instance_component_map[instance] = component_name
        elif len(parts_with_spaces) == 2:
            # Format: 'a - b' -> component: 'a'
            component_name = parts_with_spaces[0].strip()
            instance_component_map[instance] = component_name
        else:
            # Try splitting by '-' (hyphen without spaces)
            parts_no_spaces = instance.split('-')
            
            if len(parts_no_spaces) >= 3:
                # Format: 'a-b-c' -> component: 'a-b'
                component_name = '-'.join(parts_no_spaces[:2]).strip()
                instance_component_map[instance] = component_name
            elif len(parts_no_spaces) == 2:
                # Format: 'a-b' -> component: 'a'
                component_name = parts_no_spaces[0].strip()
                instance_component_map[instance] = component_name
            else:
                # No hyphens found, skip this instance
                skipped_count += 1
                logger.debug(f"Skipping instance (no hyphens): {instance}")
    
    logger.info(f"Extracted components for {len(instance_component_map)} instances")
    logger.info(f"Skipped {skipped_count} instances (no hyphens)")
    return instance_component_map


def batch_update_component_names(project_name: str, instance_component_map: dict, logger):
    """Update component names in InsightFinder via API"""
    url = (
        f"{config.insightfinder_url}/api/v1/agent-upload-instancemetadata"
        f"?userName={config.insightfinder_username}"
        f"&licenseKey={config.license_key}"
        f"&projectName={project_name}"
        f"&override=true"
    )

    # Build request body
    json_body = []
    for instance, component in instance_component_map.items():
        json_body.append({
            "instanceName": instance,
            "componentName": component
        })

    headers = {
        'Content-Type': 'application/json'
    }

    logger.debug(f"Updating {len(json_body)} instances")

    response = requests.post(url, headers=headers, data=json.dumps(json_body))
    
    if response.status_code == 200:
        logger.info(f"Successfully updated component names for project {project_name}")
        return True
    else:
        logger.error(f"Failed to update component names. Status: {response.status_code}, Response: {response.text}")
        return False


def save_mapping_to_file(instance_component_map, filename="instance_component_mapping.json"):
    """Save the instance-component mapping to a JSON file for review"""
    try:
        with open(filename, 'w') as f:
            json.dump(instance_component_map, f, indent=2)
        print(f"Mapping saved to {filename}")
        return True
    except Exception as e:
        print(f"Failed to save mapping: {e}")
        return False


def main():
    """Main function"""
    logger = setup_logging()
    
    project_name = config.insightfinder_project
    
    if not project_name:
        logger.error("Project name not configured in config.py")
        sys.exit(1)
    
    # Step 1: Login to InsightFinder
    logger.info("Logging in to InsightFinder...")
    session = requests.Session()
    token = login(session)
    logger.info("Successfully logged in")
    
    # Step 2: Fetch project metadata
    logger.info(f"Fetching metadata for project: {project_name}")
    project_metadata = get_project_metadata(session, token, project_name)
    
    # Step 3: Extract instance names
    logger.info("Extracting instance names...")
    instances = extract_instances_from_metadata(project_metadata, logger)
    logger.info(f"Found {len(instances)} instances")
    
    # Log first few instances for debugging
    if instances:
        logger.info("Sample instances:")
        for i, inst in enumerate(instances[:5]):
            logger.info(f"  {i+1}. '{inst}'")
    
    if not instances:
        logger.error("No instances found in project")
        sys.exit(1)
    
    # Step 4: Extract component names from instance names
    logger.info("Extracting component names from instance names...")
    instance_component_map = extract_component_names(instances, logger)
    
    # Step 5: Save mapping to file for review
    logger.info("Saving mapping to file...")
    save_mapping_to_file(instance_component_map)
    
    # Step 6: Update component names in InsightFinder
    logger.info("Updating component names in InsightFinder...")
    if not batch_update_component_names(project_name, instance_component_map, logger):
        logger.error("Failed to update component names")
        sys.exit(1)
    
    logger.info("Process completed successfully!")


if __name__ == "__main__":
    main()
