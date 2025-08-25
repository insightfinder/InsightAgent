#!/usr/bin/env python3
"""
Script to generate .ini files for Zabbix host groups.
This script:
1. Reads all host groups from Zabbix
2. Checks for existing .ini files in the conf.d directory
3. Creates missing .ini files using config.ini.template as a Jinja2 template
"""

import json
import logging
import os
import re
import sys
from pathlib import Path

from jinja2 import Template
from pyzabbix import ZabbixAPI

# =============================================================================
# CONFIGURATION - Update these values for your Zabbix server
# =============================================================================
ZABBIX_CONFIG = {
    'url': 'http://localhost:9999/zabbix/',
    'user': 'insight.finder', 
    'password': '2ri2T*%HKxbs',
    'request_timeout': 60
}

# Paths configuration
TEMPLATE_FILE = "zabbix.ini.template"
OUTPUT_DIR = "conf.d"
INI_SUFFIX = "-metrics.ini"
LOG_FILE = "hostgroups_status.log"
# =============================================================================

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Set up file logger for detailed hostgroup tracking
def setup_file_logger():
    """Set up a separate file logger for hostgroup status tracking"""
    file_logger = logging.getLogger('hostgroup_tracker')
    file_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for handler in file_logger.handlers[:]:
        file_logger.removeHandler(handler)
    
    # Create file handler
    file_handler = logging.FileHandler(LOG_FILE, mode='w')  # Overwrite each time
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    file_logger.addHandler(file_handler)
    
    return file_logger


def sanitize_filename(hostgroup_name):
    """
    Convert host group name to filename format.
    Replace whitespace and special characters with hyphens.
    Preserves leading hyphens from original host group name.
    """
    # Replace whitespace, underscores, and special characters with hyphens
    sanitized = re.sub(r'[^\w\-]', '-', hostgroup_name)
    # Replace underscores with hyphens too
    sanitized = sanitized.replace('_', '-')
    # Replace multiple consecutive hyphens with single hyphen
    sanitized = re.sub(r'-+', '-', sanitized)
    # Remove only trailing hyphens, preserve leading hyphens
    sanitized = sanitized.rstrip('-')
    return sanitized


def filename_to_hostgroup(filename):
    """
    Convert filename back to potential host group name for comparison.
    This is used to match existing files to host groups.
    """
    # Remove the -metrics.ini suffix
    if filename.endswith(INI_SUFFIX):
        base_name = filename[:-len(INI_SUFFIX)]
        return base_name
    return filename


def connect_to_zabbix():
    """Connect to Zabbix API using embedded configuration"""
    try:
        zapi = ZabbixAPI(server=ZABBIX_CONFIG['url'], timeout=ZABBIX_CONFIG['request_timeout'])
        zapi.session.verify = False  # Disable SSL verification
        zapi.login(user=ZABBIX_CONFIG['user'], password=ZABBIX_CONFIG['password'])
        logger.info(f"Connected to Zabbix API Version {zapi.api_version()}")
        return zapi
    except Exception as e:
        logger.error(f"Failed to connect to Zabbix: {e}")
        logger.error("Please check the ZABBIX_CONFIG values in the script")
        sys.exit(1)


def get_host_groups(zapi):
    """Retrieve all host groups from Zabbix"""
    try:
        logger.info("Retrieving all host groups from Zabbix...")
        
        # Get all host groups with extended output
        host_groups_req_params = {'output': 'extend'}
        host_groups_res = zapi.do_request('hostgroup.get', host_groups_req_params)
        
        host_groups = []
        for item in host_groups_res['result']:
            group_id = item['groupid']
            name = item['name']
            host_groups.append({
                'groupid': group_id,
                'name': name,
                'sanitized_name': sanitize_filename(name)
            })
        
        logger.info(f"Found {len(host_groups)} host groups")
        return host_groups
        
    except Exception as e:
        logger.error(f"Error retrieving host groups: {e}")
        sys.exit(1)


def get_existing_ini_files():
    """Get list of existing .ini files in the conf.d directory"""
    try:
        conf_dir = Path(OUTPUT_DIR)
        if not conf_dir.exists():
            logger.warning(f"Configuration directory {OUTPUT_DIR} does not exist")
            return set()
        
        ini_files = set()
        for file_path in conf_dir.glob(f"*{INI_SUFFIX}"):
            # Extract the base name (without -metrics.ini suffix)
            base_name = filename_to_hostgroup(file_path.name)
            ini_files.add(base_name)
        
        logger.info(f"Found {len(ini_files)} existing .ini files")
        return ini_files
        
    except Exception as e:
        logger.error(f"Error reading existing .ini files: {e}")
        return set()


def load_template():
    """Load the Jinja2 template from config.ini.template"""
    try:
        template_path = Path(TEMPLATE_FILE)
        if not template_path.exists():
            logger.error(f"Template file not found: {TEMPLATE_FILE}")
            sys.exit(1)
        
        with open(template_path, 'r') as f:
            template_content = f.read()
        
        # Create Jinja2 template
        template = Template(template_content)
        logger.info(f"Loaded template from {TEMPLATE_FILE}")
        return template
        
    except Exception as e:
        logger.error(f"Error loading template: {e}")
        sys.exit(1)


def create_ini_file(host_group, template):
    """Create an .ini file for a host group using the template"""
    try:
        sanitized_name = host_group['sanitized_name']
        filename = f"{sanitized_name}{INI_SUFFIX}"
        filepath = Path(OUTPUT_DIR) / filename
        
        # Prepare template variables
        template_vars = {
            'host_group_name': host_group['name'],
            'host_group_id': host_group['groupid'],
            'sanitized_name': sanitized_name
        }
        
        # Render the template
        rendered_content = template.render(**template_vars)
        
        # Write the file
        with open(filepath, 'w') as f:
            f.write(rendered_content)
        
        logger.info(f"Created: {filepath}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating .ini file for {host_group['name']}: {e}")
        return False


def find_missing_host_groups(host_groups, existing_files):
    """Find host groups that don't have corresponding .ini files"""
    missing = []
    
    for host_group in host_groups:
        sanitized_name = host_group['sanitized_name']
        
        # Check if a file exists for this host group
        if sanitized_name not in existing_files:
            missing.append(host_group)
    
    return missing


def log_hostgroup_status(host_groups, existing_files, missing_host_groups, file_logger):
    """Log detailed status of host groups to the log file"""
    file_logger.info("=" * 80)
    file_logger.info("ZABBIX HOST GROUP STATUS REPORT")
    file_logger.info("=" * 80)
    file_logger.info(f"Total host groups in Zabbix: {len(host_groups)}")
    file_logger.info(f"Existing .ini files: {len(existing_files)}")
    file_logger.info(f"Missing .ini files: {len(missing_host_groups)}")
    file_logger.info("")
    
    # Log existing host groups with files
    existing_host_groups = [hg for hg in host_groups if hg['sanitized_name'] in existing_files]
    if existing_host_groups:
        file_logger.info("HOST GROUPS WITH EXISTING .ini FILES:")
        file_logger.info("-" * 50)
        for i, hg in enumerate(existing_host_groups, 1):
            filename = f"{hg['sanitized_name']}{INI_SUFFIX}"
            file_logger.info(f"{i:3d}. {hg['name']} (ID: {hg['groupid']}) -> {filename}")
        file_logger.info("")
    
    # Log missing host groups
    if missing_host_groups:
        file_logger.info("HOST GROUPS WITHOUT .ini FILES (TO BE CREATED):")
        file_logger.info("-" * 50)
        for i, hg in enumerate(missing_host_groups, 1):
            filename = f"{hg['sanitized_name']}{INI_SUFFIX}"
            file_logger.info(f"{i:3d}. {hg['name']} (ID: {hg['groupid']}) -> {filename}")
        file_logger.info("")
    else:
        file_logger.info("All host groups have corresponding .ini files!")
        file_logger.info("")
    
    # Log filename sanitization examples
    file_logger.info("FILENAME SANITIZATION EXAMPLES:")
    file_logger.info("-" * 50)
    examples = host_groups[:10]  # Show first 10 as examples
    for i, hg in enumerate(examples, 1):
        original = hg['name']
        sanitized = hg['sanitized_name']
        if original != sanitized:
            file_logger.info(f"{i:2d}. '{original}' -> '{sanitized}'")
        else:
            file_logger.info(f"{i:2d}. '{original}' (no change needed)")
    
    file_logger.info("")
    file_logger.info("=" * 80)


def main():
    """Main function"""
    logger.info("Starting Zabbix Host Group .ini File Generator")
    logger.info(f"Template file: {TEMPLATE_FILE}")
    logger.info(f"Output directory: {OUTPUT_DIR}")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info(f"Zabbix server: {ZABBIX_CONFIG['url']}")
    
    # Set up file logger
    file_logger = setup_file_logger()
    file_logger.info("Starting Zabbix Host Group analysis")
    
    # Connect to Zabbix
    zapi = connect_to_zabbix()
    
    # Get host groups from Zabbix
    host_groups = get_host_groups(zapi)
    
    # Get existing .ini files
    existing_files = get_existing_ini_files()
    
    # Load template
    template = load_template()
    
    # Find missing host groups
    missing_host_groups = find_missing_host_groups(host_groups, existing_files)
    
    # Log detailed status to file
    log_hostgroup_status(host_groups, existing_files, missing_host_groups, file_logger)
    
    if not missing_host_groups:
        logger.info("All host groups already have corresponding .ini files!")
        file_logger.info("No new files needed - all host groups have .ini files")
        print(f"\nSummary:")
        print(f"Total host groups: {len(host_groups)}")
        print(f"Existing .ini files: {len(existing_files)}")
        print(f"Missing .ini files: 0")
        print(f"📄 Detailed log written to: {LOG_FILE}")
        return
    
    logger.info(f"Found {len(missing_host_groups)} host groups without .ini files")
    file_logger.info(f"Creating {len(missing_host_groups)} new .ini files")
    
    # Create missing .ini files
    created_count = 0
    failed_count = 0
    
    for host_group in missing_host_groups:
        if create_ini_file(host_group, template):
            created_count += 1
            file_logger.info(f"Successfully created: {host_group['sanitized_name']}{INI_SUFFIX} for '{host_group['name']}'")
        else:
            failed_count += 1
            file_logger.error(f"Failed to create: {host_group['sanitized_name']}{INI_SUFFIX} for '{host_group['name']}'")
    
    # Final summary to file
    file_logger.info("")
    file_logger.info("FINAL SUMMARY:")
    file_logger.info("-" * 30)
    file_logger.info(f"Total host groups processed: {len(host_groups)}")
    file_logger.info(f"Files successfully created: {created_count}")
    file_logger.info(f"Files failed to create: {failed_count}")
    file_logger.info(f"Total .ini files now exist: {len(existing_files) + created_count}")
    
    # Summary
    logger.info("Script completed!")
    print(f"\nSummary:")
    print(f"Total host groups: {len(host_groups)}")
    print(f"Existing .ini files: {len(existing_files)}")
    print(f"Missing .ini files found: {len(missing_host_groups)}")
    print(f"Successfully created: {created_count}")
    print(f"Failed to create: {failed_count}")
    print(f"📄 Detailed log written to: {LOG_FILE}")
    
    if failed_count > 0:
        print(f"\n⚠️  {failed_count} files failed to create. Check the logs for details.")
    
    # Show some examples of what was created
    if created_count > 0:
        print(f"\nExamples of created files:")
        for i, host_group in enumerate(missing_host_groups[:5]):  # Show first 5
            if i < created_count:
                filename = f"{host_group['sanitized_name']}{INI_SUFFIX}"
                print(f"  {host_group['name']} -> {filename}")


if __name__ == "__main__":
    main()
