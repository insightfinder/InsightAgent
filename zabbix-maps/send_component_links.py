#!/usr/bin/env python3
"""
Script to send component links to InsightFinder API
Reads component_links.json and sends the data to InsightFinder
"""

import json
import sys
import logging
import requests
import time
import config

# Input configuration
COMPONENT_LINKS_FILE = 'component_links.json'
LOG_LEVEL = logging.INFO

# InsightFinder API configuration
INSIGHTFINDER_URL = 'https://stg.insightfinder.com/api/v2/updaterelationdependency'

def setup_logging():
    """Setup basic logging"""
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def load_component_links(logger, filename):
    """Load component links from JSON file"""
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        
        # Extract just the component_links array
        component_links = data.get('component_links', [])
        logger.info(f"Loaded {len(component_links)} component links from {filename}")
        return component_links
    except FileNotFoundError:
        logger.error(f"File not found: {filename}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filename}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
        return None

def send_to_insightfinder(logger, component_links):
    """
    Send component links to InsightFinder API
    
    Args:
        component_links: List of dicts with 's' (source) and 't' (target)
    
    Returns:
        Boolean indicating success
    """
    try:
        # Transform component links to the correct format with nested structure
        component_relation_list = []
        for link in component_links:
            relation = {
                "s": {
                    "id": link["s"],
                    "type": "componentLevel"
                },
                "t": {
                    "id": link["t"],
                    "type": "componentLevel"
                }
            }
            component_relation_list.append(relation)
        
        # Convert to JSON string as required by the API
        component_relation_list_str = json.dumps(component_relation_list)
        
        # Create payload with correct parameter names
        payload = {
            "systemDisplayName": config.insightfinder_system,
            "licenseKey": config.license_key,
            "userName": config.insightfinder_username,
            "dailyTimestamp": int(time.time() * 1000),  # Current timestamp in milliseconds
            "projectLevelAddRelationSetStr": component_relation_list_str
        }
        
        logger.info(f"Sending {len(component_links)} component relations to InsightFinder...")
        logger.info(f"API URL: {INSIGHTFINDER_URL}")
        logger.info(f"Project: {config.insightfinder_project}")
        logger.info(f"\nPayload parameters:")
        logger.info(f"  systemDisplayName: {payload['systemDisplayName']}")
        logger.info(f"  userName: {payload['userName']}")
        logger.info(f"  licenseKey: {payload['licenseKey'][:20]}...{payload['licenseKey'][-10:]}")
        logger.info(f"  dailyTimestamp: {payload['dailyTimestamp']}")
        logger.info(f"  projectLevelAddRelationSetStr (first 200 chars): {component_relation_list_str[:200]}...")
        
        # Save the full payload to a file for debugging
        with open('last_api_payload.json', 'w') as f:
            json.dump(payload, f, indent=2)
        logger.info(f"\nFull payload saved to last_api_payload.json")
        
        response = requests.post(
            INSIGHTFINDER_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            verify=False  # Skip SSL verification
        )
        
        if response.status_code == 200:
            logger.info("Successfully sent component links to InsightFinder!")
            # Try to parse JSON response, but handle empty/non-JSON responses
            try:
                response_data = response.json()
                logger.info(f"Response: {response_data}")
            except:
                logger.info(f"Response (text): {response.text if response.text else 'Empty response'}")
            return True
        else:
            logger.error(f"Error sending data: {response.status_code}")
            logger.error(f"Response: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to send data to InsightFinder: {e}")
        return False

def main():
    """Main function"""
    logger = setup_logging()
    
    # Load component links
    logger.info(f"Loading component links from {COMPONENT_LINKS_FILE}...")
    component_links = load_component_links(logger, COMPONENT_LINKS_FILE)
    
    if component_links is None:
        logger.error("Failed to load component links. Please run create_component_links.py first.")
        sys.exit(1)
    
    if not component_links:
        logger.warning("No component links found to send.")
        sys.exit(1)
    
    # Display summary
    logger.info(f"\nComponent Links Summary:")
    logger.info(f"  Total links: {len(component_links)}")
    
    # Show first few links as examples
    logger.info(f"\nFirst 5 component links:")
    for i, link in enumerate(component_links[:5], 1):
        logger.info(f"  {i}. {link['s']} -> {link['t']}")
    
    if len(component_links) > 5:
        logger.info(f"  ... and {len(component_links) - 5} more")
    
    # Send to InsightFinder
    logger.info(f"\n{'='*60}")
    if not send_to_insightfinder(logger, component_links):
        logger.error("Failed to send component links to InsightFinder")
        sys.exit(1)
    
    logger.info("Component links sent successfully!")

if __name__ == "__main__":
    main()
