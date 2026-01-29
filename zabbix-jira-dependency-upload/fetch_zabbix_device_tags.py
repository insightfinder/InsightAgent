#!/usr/bin/env python3
"""
Simple script to fetch all devices from Zabbix with their tags 
for 'jira_upstream_device_name' and 'jira_venue_key' and store in YAML.
"""

import yaml
import logging
from pyzabbix import ZabbixAPI
import config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fetch_devices_with_tags():
    """
    Fetch all devices from Zabbix with their tags.
    Returns a dictionary with hostname as key and tags as subkeys.
    """
    logger.info("Connecting to Zabbix...")
    
    # Connect to Zabbix API
    zapi = ZabbixAPI(server=config.zabbix_url, timeout=60)
    zapi.session.verify = False
    zapi.login(user=config.zabbix_user, password=config.zabbix_password)
    
    logger.info(f"Connected to Zabbix API Version {zapi.api_version()}")
    
    # Fetch all hosts with their tags
    logger.info("Fetching all hosts with tags...")
    hosts = zapi.host.get(
        output=['hostid', 'host', 'name'],
        selectTags='extend'
    )
    
    logger.info(f"Found {len(hosts)} hosts in Zabbix")
    
    # Process hosts and extract relevant tags
    devices_data = {}
    hosts_with_tags = 0
    
    for host in hosts:
        hostname = host['host']
        tags = {}
        
        # Extract specific tags
        if 'tags' in host and host['tags']:
            for tag in host['tags']:
                tag_name = tag.get('tag', '')
                tag_value = tag.get('value', '')
                
                # Only store the tags we're interested in
                if tag_name in ['jira_upstream_device_name', 'jira_venue_key']:
                    tags[tag_name] = tag_value
            
            # Only include devices that have at least one of the tags we care about
            if tags:
                devices_data[hostname] = tags
                hosts_with_tags += 1
        
    logger.info(f"Found {hosts_with_tags} hosts with relevant tags")
    
    return devices_data


def save_to_yaml(devices_data, output_file='zabbix_devices_tags.yaml'):
    """
    Save devices data to a YAML file.
    """
    logger.info(f"Saving data to {output_file}...")
    
    with open(output_file, 'w') as f:
        yaml.dump(devices_data, f, default_flow_style=False, sort_keys=False)
    
    logger.info(f"Successfully saved {len(devices_data)} devices to {output_file}")


def main():
    """Main execution function"""
    logger.info("="*80)
    logger.info("Fetching Zabbix Device Tags")
    logger.info("="*80)

    try:
        # Fetch devices with tags
        devices_data = fetch_devices_with_tags()

        # Save to YAML file
        save_to_yaml(devices_data)

        logger.info("="*80)
        logger.info("✓ Process completed successfully!")
        logger.info("="*80)

        # Print sample of data
        if devices_data:
            sample_host, sample_tags = next(iter(devices_data.items()))
            logger.info("\nSample device:")
            logger.info(f"{sample_host}: {sample_tags}")

    except Exception as e:
        logger.error(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()
