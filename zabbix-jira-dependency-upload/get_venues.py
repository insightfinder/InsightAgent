#!/usr/bin/env python3

import requests
import yaml
import config

def get_venue_assets(url, username, api_token, workspace_id, object_type):
    """
    Retrieves all venue assets from Jira Assets.
    
    Args:
        url: Jira URL
        username: Jira username
        api_token: Jira API token
        workspace_id: Jira Assets workspace ID
        object_type: The object type to fetch (e.g., 'venue')
    
    Returns:
        List of venue assets
    """
    aql_endpoint = f"https://api.atlassian.com/jsm/assets/workspace/{workspace_id}/v1/aql/objects"
    aql = f'objectType = "{object_type}"'
    print(f"Executing AQL query: {aql}")
    
    headers = {"Accept": "application/json"}
    all_venues = []
    page = 1
    results_per_page = 25

    while True:
        params = {"qlQuery": aql, "page": page, "resultsPerPage": results_per_page}
        try:
            response = requests.get(
                aql_endpoint, 
                headers=headers, 
                params=params, 
                auth=(username, api_token), 
                timeout=60
            )
            print(f"Request for page {page} completed with status code: {response.status_code}")
            response.raise_for_status()
            
            data = response.json()
            assets_on_page = data.get("objectEntries", [])
            all_venues.extend(assets_on_page)
            
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
    
    return all_venues

def extract_venue_info(venues):
    """
    Extracts venue name and ID from the raw venue assets.
    
    Args:
        venues: List of venue asset objects
    
    Returns:
        Dictionary with venue key as key, and venue name as value
    """
    venue_info = {}
    
    for venue in venues:
        venue_key = venue.get("objectKey")
        venue_label = venue.get("label")
        
        if venue_key and venue_label:
            venue_info[venue_key] = venue_label
    
    return venue_info

def main():
    """Main function to fetch venue assets and save to file."""
    # Fetch all venue assets
    print("Fetching all venue assets...")
    venues = get_venue_assets(
        config.jira_url, 
        config.jira_username, 
        config.jira_api_token, 
        config.jira_workspace_id, 
        "venue"
    )
    
    if not venues:
        print("No venue assets found.")
        return
    
    print(f"Found {len(venues)} venue assets.")
    
    # Extract venue information
    venue_info = extract_venue_info(venues)
    
    # Save to YAML file
    with open("venues.yaml", "w") as f:
        yaml.dump(venue_info, f, indent=2, sort_keys=False)
    
    print(f"Successfully saved {len(venue_info)} venues to venues.yaml")
    
    # Print summary
    print("\n--- Venue Summary ---")
    for key, name in venue_info.items():
        print(f"{key}: {name}")

if __name__ == "__main__":
    main()
