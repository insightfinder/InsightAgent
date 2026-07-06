#!/usr/bin/env python3

import configparser
import requests
import json
import time
import multiprocessing
import yaml

def get_assets_batch(args):
    """
    Worker function to retrieve a batch of assets.
    """
    url, username, api_token, workspace_id, object_type, aql_extra = args
    aql_endpoint = f"https://api.atlassian.com/jsm/assets/workspace/{workspace_id}/v1/aql/objects"
    aql = f'objectType = "{object_type}" {aql_extra}'
    print(f"Executing AQL query: {aql}")
    headers = {"Accept": "application/json"}
    all_assets = []
    page = 1
    results_per_page = 25

    while True:
        params = {"qlQuery": aql, "page": page, "resultsPerPage": results_per_page}
        try:
            response = requests.get(aql_endpoint, headers=headers, params=params, auth=(username, api_token), timeout=60)
            print(f"Request for page {page} completed with status code: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            assets_on_page = data.get("objectEntries", [])
            all_assets.extend(assets_on_page)
            if len(assets_on_page) < results_per_page:
                break
            page += 1
        except requests.exceptions.Timeout:
            print(f"Request for page {page} timed out after 60 seconds.")
            return None
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            if e.response:
                print(f"Response content: {e.response.text}")
            return None
    return all_assets

def simplify_hierarchy(hierarchy, hierarchy_config):
    """
    Recursively simplifies the hierarchy to include only name and id, and uses the object type as the key for children.
    """
    simplified = {}
    for key, value in hierarchy.items():
        current_object_type = value["details"]["objectType"]["name"]
        
        simplified_value = {
            "details": {
                "id": value["details"].get("id"),
                "name": value["details"].get("label")
            }
        }

        child_object_type = None
        for p_type, c_type in hierarchy_config:
            if p_type.lower() == current_object_type.lower():
                child_object_type = c_type
                break
        
        if child_object_type and "children" in value and value["children"]:
            simplified_value[child_object_type] = simplify_hierarchy(value["children"], hierarchy_config)
        
        simplified[key] = simplified_value
    return simplified

def main():
    total_start_time = time.time()
    config = configparser.ConfigParser()
    config.read("conf.d/config.ini")

    try:
        jira_url = config.get("Jira", "url")
        jira_username = config.get("Jira", "username")
        jira_api_token = config.get("Jira", "api_token")
        workspace_id = config.get("Jira", "workspace_id")
        batch_size = config.getint("Jira", "batch_size", fallback=50)
        hierarchy = config.items("Hierarchy")
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        print(f"Error reading configuration from config.ini: {e}")
        return

    # Fetch all assets at each level of the hierarchy
    assets_by_type = {}
    all_assets_map = {}
    parent_keys = None
    parent_object_type = None

    for parent_type, child_type in hierarchy:
        if parent_object_type is None:
            # First level of the hierarchy
            print(f"Fetching all {parent_type} assets...")
            assets = get_assets_batch((jira_url, jira_username, jira_api_token, workspace_id, parent_type, ""))
            if not assets:
                print(f"No {parent_type} assets found. Aborting.")
                return
            assets_by_type[parent_type] = {asset["objectKey"]: {"details": asset, "children": {}} for asset in assets}
            for asset in assets:
                all_assets_map[asset["objectKey"]] = asset
            parent_keys = list(assets_by_type[parent_type].keys())
        
        print(f"Fetching {child_type} assets...")
        child_assets = []
        if not parent_keys:
            print(f"No parent keys found for {child_type}, skipping.")
            continue
            
        tasks = []
        for i in range(0, len(parent_keys), batch_size):
            batch_keys = parent_keys[i:i + batch_size]
            parent_keys_str = ",".join([f'\"{key}\"' for key in batch_keys])
            # We assume the attribute name on the child object is the same as the parent object type name
            aql_extra = f'AND "{parent_type}" IN ({parent_keys_str})'
            tasks.append((jira_url, jira_username, jira_api_token, workspace_id, child_type, aql_extra))

        with multiprocessing.Pool(processes=8) as pool:
            results = pool.map(get_assets_batch, tasks)
        
        for result in results:
            if result:
                child_assets.extend(result)

        if child_assets:
            assets_by_type[child_type] = {asset["objectKey"]: {"details": asset, "children": {}} for asset in child_assets}
            for asset in child_assets:
                all_assets_map[asset["objectKey"]] = asset
            parent_keys = list(assets_by_type[child_type].keys())
        else:
            print(f"No {child_type} assets found.")
            parent_keys = []

        parent_object_type = child_type

    # Build the hierarchy
    for parent_type, child_type in reversed(hierarchy):
        if child_type not in assets_by_type:
            continue

        for child_key, child_value in assets_by_type[child_type].items():
            child_full_details = all_assets_map.get(child_key)
            if not child_full_details:
                continue

            for attribute in child_full_details.get("attributes", []):
                for value in attribute.get("objectAttributeValues", []):
                    if value.get("referencedObject"):
                        referenced_object = value["referencedObject"]
                        if referenced_object.get("objectType", {}).get("name", "").lower() == parent_type.lower():
                            parent_key = referenced_object.get("objectKey")
                            if parent_type in assets_by_type and parent_key in assets_by_type[parent_type]:
                                assets_by_type[parent_type][parent_key]["children"][child_key] = child_value

    # Get the top-level of the hierarchy to save to the file
    top_level_type = hierarchy[0][0]
    final_hierarchy = assets_by_type.get(top_level_type, {})

    # Simplify the hierarchy for the final output
    simplified_hierarchy = simplify_hierarchy(final_hierarchy, hierarchy)

    with open("asset_hierarchy.yaml", "w") as f:
        yaml.dump(simplified_hierarchy, f, indent=2)

    total_end_time = time.time()
    print(f"Successfully created asset hierarchy in asset_hierarchy.yaml in {total_end_time - total_start_time:.2f} seconds.")

if __name__ == "__main__":
    main()