#!/usr/bin/env python3
"""
Script to send device relationships to InsightFinder API.
Reads from zabbix_devices_tags.yaml and venues.yaml.
"""

import yaml
import json
import logging
import requests
import re
import sys
import config

# Regular expressions for safe string conversion
UNDERSCORE = re.compile(r"\_+")
COLONS = re.compile(r"\:+")
LEFT_BRACE = re.compile(r"\[")
RIGHT_BRACE = re.compile(r"\]")
PERIOD = re.compile(r"\.")
COMMA = re.compile(r"\,")

# Configuration
INSIGHTFINDER_API_URL = config.insightfinder_url + '/api/v2/updaterelationdependency'
TEST_LIMIT = 0  # Limit number of relations to send for testing (set to 0 to send all)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def make_safe_instance_string(instance, device=''):
    """Make a safe instance name string for InsightFinder"""
    instance = UNDERSCORE.sub('.', instance)
    instance = COLONS.sub('-', instance)
    instance = re.sub(r'^[-_\W]+', '', instance)
    if device:
        instance = '{}_{}'.format(make_safe_instance_string(device), instance)
    return instance


def load_yaml_file(filepath):
    """Load YAML file and return data"""
    try:
        with open(filepath, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
        raise


def process_device_relations(devices_data, venues_data):
    """
    Process device relations from the YAML data.
    Returns list of relations with source, target, and zone name.
    """
    relations = []
    skipped_empty = 0

    for device_name, device_tags in devices_data.items():
        # Get upstream device name (source in InsightFinder)
        upstream_device = device_tags.get('jira_upstream_device_name', '')

        # Skip if upstream device name is empty
        if not upstream_device or upstream_device.strip() == '':
            skipped_empty += 1
            continue

        # Get venue key
        venue_key = device_tags.get('jira_venue_key', '')

        # Look up venue name from venues.yaml
        zone_name = venues_data.get(venue_key, 'NO_ZONE')

        # Sanitize device names for InsightFinder
        safe_source = make_safe_instance_string(upstream_device)
        safe_target = make_safe_instance_string(device_name)

        relations.append({
            'source': safe_source,
            'target': safe_target,
            'zone_name': zone_name,
            'original_source': upstream_device,
            'original_target': device_name
        })

    logger.info(f"Processed {len(relations)} valid device relations")
    logger.info(f"Skipped {skipped_empty} devices with empty upstream device name")

    return relations


def send_relations_to_insightfinder(relations):
    """
    Send device relations to InsightFinder API.
    Groups relations by zone and sends one request per zone.
    """
    # Group relations by zone
    relations_by_zone = {}
    for relation in relations:
        zone_name = relation['zone_name']
        if zone_name not in relations_by_zone:
            relations_by_zone[zone_name] = []
        relations_by_zone[zone_name].append(relation)
    
    logger.info(f"Relations grouped into {len(relations_by_zone)} zones")
    
    total_sent = 0
    total_failed = 0
    
    # Send relations for each zone
    for zone_name, zone_relations in relations_by_zone.items():
        logger.info(f"\nProcessing zone: '{zone_name}' ({len(zone_relations)} relations)")
        
        # Build instance relation list for API
        instance_relation_list = []
        for rel in zone_relations:
            instance_relation_list.append({
                "s": {
                    "id": rel['source'],
                    "type": "componentLevel"
                },
                "t": {
                    "id": rel['target'],
                    "type": "componentLevel"
                }
            })
        
        # Convert to JSON string
        instance_relation_list_str = json.dumps(instance_relation_list)
        
        # Create payload
        payload = {
            "systemDisplayName": config.insightfinder_system,
            "licenseKey": config.license_key,
            "userName": config.insightfinder_username,
            "projectLevelAddRelationSetStr": instance_relation_list_str,
            "zoneName": zone_name
        }
        
        try:
            response = requests.post(
                INSIGHTFINDER_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                verify=False
            )
            
            if response.status_code == 200:
                logger.info(f"  ✓ Successfully sent {len(zone_relations)} relations for zone '{zone_name}'")
                total_sent += len(zone_relations)
            else:
                logger.error(f"  ✗ Failed to send relations for zone '{zone_name}': {response.status_code}")
                logger.error(f"    Response: {response.text}")
                total_failed += len(zone_relations)
        except Exception as e:
            logger.error(f"  ✗ Error sending relations for zone '{zone_name}': {e}")
            total_failed += len(zone_relations)
    
    return total_sent, total_failed


def main():
    """Main execution function"""
    logger.info("="*80)
    logger.info("Sending Device Relations to InsightFinder")
    if TEST_LIMIT > 0:
        logger.info(f"TEST MODE: Limiting to first {TEST_LIMIT} relations")
    logger.info("="*80)
    
    try:
        # Load YAML files
        logger.info("\n[1/4] Loading YAML files...")
        devices_data = load_yaml_file('zabbix_devices_tags.yaml')
        venues_data = load_yaml_file('venues.yaml')
        logger.info(f"  Loaded {len(devices_data)} devices")
        logger.info(f"  Loaded {len(venues_data)} venues")
        
        # Process device relations
        logger.info("\n[2/4] Processing device relations...")
        relations = process_device_relations(devices_data, venues_data)
        
        # Apply test limit if configured
        if TEST_LIMIT > 0 and len(relations) > TEST_LIMIT:
            logger.info(f"\n[TEST MODE] Limiting from {len(relations)} to {TEST_LIMIT} relations")
            relations = relations[:TEST_LIMIT]
        
        if not relations:
            logger.warning("No valid relations to send!")
            return
        
        # Show sample relations
        logger.info("\n[3/4] Sample relations (first 3):")
        for i, rel in enumerate(relations[:3], 1):
            logger.info(f"  {i}. {rel['original_source']} -> {rel['original_target']}")
            logger.info(f"     Sanitized: {rel['source']} -> {rel['target']}")
            logger.info(f"     Zone: {rel['zone_name']}")
        
        # Send to InsightFinder
        logger.info(f"\n[4/4] Sending {len(relations)} relations to InsightFinder...")
        total_sent, total_failed = send_relations_to_insightfinder(relations)
        
        # Final summary
        logger.info("\n" + "="*80)
        logger.info("SUMMARY")
        logger.info("="*80)
        logger.info(f"Total relations processed: {len(relations)}")
        logger.info(f"Successfully sent: {total_sent}")
        logger.info(f"Failed: {total_failed}")
        logger.info("="*80)
        
        if total_sent > 0:
            logger.info("\n✓ Process completed successfully!")
        else:
            logger.error("\n✗ No relations were sent successfully!")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"\n✗ Error: {e}")
        raise


if __name__ == "__main__":
    main()
