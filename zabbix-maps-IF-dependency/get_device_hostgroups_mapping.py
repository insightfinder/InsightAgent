#!/usr/bin/env python3
"""
Script to fetch all Zabbix devices and their respective host groups.
Creates a mapping/list of devices with their host group memberships.
"""

import json
import logging
import sys
from pyzabbix import ZabbixAPI
import config

# Output configuration
OUTPUT_FILE = 'device_hostgroups_mapping.json'
LOG_LEVEL = logging.INFO


def setup_logging():
    """Setup basic logging"""
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def connect_to_zabbix(logger):
    """Connect to Zabbix API"""
    try:
        logger.info(f"Connecting to Zabbix at {config.zabbix_url}")
        zapi = ZabbixAPI(server=config.zabbix_url, timeout=60)
        zapi.session.verify = False
        zapi.login(user=config.zabbix_user, password=config.zabbix_password)
        logger.info(f"Connected to Zabbix API Version {zapi.api_version()}")
        return zapi
    except Exception as e:
        logger.error(f"Failed to connect to Zabbix: {e}")
        return None


def fetch_device_hostgroups_mapping(logger, zapi):
    """Fetch all devices and their host groups from Zabbix"""
    try:
        logger.info("Fetching host groups...")
        
        # Step 1: Get all host groups
        host_groups_res = zapi.do_request('hostgroup.get', {'output': 'extend'})
        host_groups_ids = [item['groupid'] for item in host_groups_res['result']]
        
        logger.info(f"Found {len(host_groups_ids)} host groups")
        
        # Step 2: Get all hosts with their host groups
        logger.info("Fetching devices and their host group memberships...")
        hosts_res = zapi.do_request('host.get', {
            'output': ['host'],
            'groupids': host_groups_ids,
            'selectHostGroups': ['name']
        })
        
        logger.info(f"Found {len(hosts_res['result'])} devices")
        
        # Step 3: Process and structure the data as key-value pairs
        device_mapping = {}
        
        for host in hosts_res['result']:
            # Extract host group names
            hostgroups = host.get('hostgroups') or []
            host_group_names = [hg.get('name', '') for hg in hostgroups]
            
            # Create key-value pair: hostname -> host_groups
            device_mapping[host['host']] = host_group_names
        
        logger.info(f"Processed {len(device_mapping)} devices")
        
        return device_mapping
        
    except Exception as e:
        logger.error(f"Failed to fetch device-hostgroup mapping: {e}")
        logger.error(f"Error details: {str(e)}")
        return None


def save_to_file(logger, mapping_data, filename):
    """Save mapping data to JSON file"""
    try:
        with open(filename, 'w') as f:
            json.dump(mapping_data, f, indent=2)
        logger.info(f"Device-hostgroup mapping saved to {filename}")
        
        # Print summary
        logger.info(f"\nSummary:")
        logger.info(f"  Total devices: {len(mapping_data)}")
        
        return True
    except Exception as e:
        logger.error(f"Failed to save to file: {e}")
        return False


def main():
    """Main function"""
    logger = setup_logging()
    
    logger.info("="*80)
    logger.info("Starting Zabbix Device-HostGroup Mapping Extraction")
    logger.info("="*80)
    
    # Step 1: Connect to Zabbix
    logger.info("\n[1/3] Connecting to Zabbix...")
    zapi = connect_to_zabbix(logger)
    if not zapi:
        logger.error("Failed to connect to Zabbix")
        sys.exit(1)
    
    # Step 2: Fetch device-hostgroup mapping
    logger.info("\n[2/3] Fetching device-hostgroup mapping...")
    mapping_data = fetch_device_hostgroups_mapping(logger, zapi)
    if not mapping_data:
        logger.error("Failed to fetch mapping data")
        sys.exit(1)
    
    # Step 3: Save to file
    logger.info("\n[3/3] Saving results to file...")
    if not save_to_file(logger, mapping_data, OUTPUT_FILE):
        logger.error("Failed to save mapping data")
        sys.exit(1)
    
    logger.info("\n" + "="*80)
    logger.info("✓ Process completed successfully!")
    logger.info(f"\nOutput file: {OUTPUT_FILE}")
    logger.info("="*80)


if __name__ == "__main__":
    main()
