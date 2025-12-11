#!/usr/bin/env python3
"""
Agent to Update Zabbix metadata with tag appended
"""

import json
import logging
import sys
import re
import regex
import requests
from pyzabbix import ZabbixAPI
import config as config

# Component regex mapping for hostname
COMPONENT_REGEX_MAPPING = [
    # (r'^(?=.*he)(?=.*mikrotik|microtik).*', 'HE-Router'),
    # (r'.*he.*(mi[ck]rotik).*|.*(mi[ck]rotik).*he.*', 'HE-Router'),
    (r'.*he.*(mi[ck]rotik).*', 'HE-Router'),
    (r'.*(?!.*he).*(mi[ck]rotik).*', 'Router'),
    (r'.*(he-swt|he-sw).*', 'HE-SW'),
    (r'.*(?<!he-)(swt|sw|switch).*', 'Switch'),
    (r'.*-tn$', 'TN'),
    (r'(?i).*-bn\d*$', 'BN'),
    (r'.*rtr.*', 'Router'),
    (r'.*ap.*', 'AP'),
    (r'.*cpe.*', 'CPE'),
    (r'.*enb.*', 'eNB'),
    (r'.*esxi.*', 'ESXI'),
    (r'.*isp.*', 'ISP'),
    (r'.*olt.*', 'OLT'),
    (r'.*pdu.*', 'PDU'),
    (r'.*ptp.*', 'PTP'),
    (r'.*router.*', 'Router'),
    (r'.*smartbox.*', 'Smartbox'),
    (r'.*ups.*', 'UPS'),
    (r'.*-gam.?$', 'GAM'),
    (r'.*wan.*', 'WAN'),
    (r'.*-dn$', 'DN'),
    (r'.*-cn$', 'CN'),
]

# declare a few vars
TRUE = regex.compile(r"T(RUE)?", regex.IGNORECASE)
FALSE = regex.compile(r"F(ALSE)?", regex.IGNORECASE)
SPACES = regex.compile(r"\s+")
SLASHES = regex.compile(r"\/+")
UNDERSCORE = regex.compile(r"\_+")
COLONS = regex.compile(r"\:+")
LEFT_BRACE = regex.compile(r"\[")
RIGHT_BRACE = regex.compile(r"\]")
PERIOD = regex.compile(r"\.")
COMMA = regex.compile(r"\,")
NON_ALNUM = regex.compile(r"[^a-zA-Z0-9]")
FORMAT_STR = regex.compile(r"{(.*?)}")

# Output configuration
OUTPUT_FILE = 'zabbix_metadata.json'
MATCHED_FILE = 'zabbix_matched_components.json'
UNMATCHED_FILE = 'zabbix_unmatched_components.json'
LOG_LEVEL = logging.INFO

def setup_logging():
    """Setup basic logging"""
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def connect_to_zabbix(logger):
    """Connect to Zabbix API using exact same method as getmessages script"""
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

def fetch_metadata(logger, zapi):
    """Fetch host metadata using minimal API calls like getmessages script"""
    try:
        logger.info("Fetching host metadata...")
        
        # Step 1: Get host groups (exactly like getmessages script)
        logger.info("Query all host_groups")
        host_groups_res = zapi.do_request('hostgroup.get', {'output': 'extend'})
        host_groups_map = {}
        host_groups_ids = []
        for item in host_groups_res['result']:
            group_id = item['groupid']
            name = item['name']
            host_groups_ids.append(group_id)
            host_groups_map[group_id] = name
        
        logger.info(f"Found {len(host_groups_map)} host groups")
        
        # Step 2: Get hosts with minimal parameters
        hosts_res = zapi.do_request('host.get', {
            'output': ['name', 'hostid', 'host', 'status'],
            'groupids': host_groups_ids,
            'selectHostGroups': ['groupid', 'name'],
            'selectInterfaces': ['ip', 'type', 'main']
        })
        
        logger.info(f"Found {len(hosts_res['result'])} hosts")
        
        # Step 3: Get tags separately if hosts exist
        metadata = []
        if hosts_res['result']:
            host_ids = [host['hostid'] for host in hosts_res['result']]
            
            # Get tags separately to avoid server errors
            try:
                tags_res = zapi.do_request('host.get', {
                    'output': ['hostid'],
                    'hostids': host_ids,
                    'selectTags': 'extend'
                })
                
                # Create tags lookup
                tags_map = {}
                for host in tags_res['result']:
                    tags_map[host['hostid']] = host.get('tags', [])
                    
            except Exception as e:
                logger.warning(f"Could not fetch tags: {e}")
                tags_map = {}
        
        # Process hosts data
        for host in hosts_res['result']:
            # Extract host group names
            hostgroups = host.get('hostgroups') or []
            host_group_names = [hg.get('name', '') for hg in hostgroups]
            
            # Extract IP addresses from interfaces
            interfaces = host.get('interfaces') or []
            host_ip = ''
            ip_addresses = []
            
            # Find primary IP
            for interface in interfaces:
                if interface.get('main') == '1' and interface.get('type') == '1':
                    host_ip = interface.get('ip', '')
                    break
            
            if not host_ip:
                for interface in interfaces:
                    if interface.get('ip'):
                        host_ip = interface.get('ip', '')
                        break
            
            # Collect all IP addresses
            for interface in interfaces:
                if interface.get('ip'):
                    interface_type = 'agent' if interface.get('type') == '1' else 'other'
                    ip_addresses.append({
                        'ip': interface['ip'],
                        'type': interface_type,
                        'main': interface.get('main') == '1'
                    })
            
            host_data = {
                'hostid': host['hostid'],
                'hostname': host['host'],
                'display_name': host['name'],
                'status': 'enabled' if host['status'] == '0' else 'disabled',
                'tags': tags_map.get(host['hostid'], []),
                'host_groups': host_group_names,
                'primary_ip': host_ip,
                'all_interfaces': ip_addresses
            }
            
            metadata.append(host_data)
        
        logger.info(f"Processed metadata for {len(metadata)} hosts")
        return metadata
        
    except Exception as e:
        logger.error(f"Failed to fetch metadata: {e}")
        logger.error(f"Error details: {str(e)}")
        return None

def login(session: requests.Session):
    # Perform login request to retrieve token and session ID
    login_url = f"{config.insightfinder_url}/api/v1/login-check"
    login_params = {
        "userName": config.insightfinder_username,
        "password": config.insightfinder_password
    }

    login_response = session.post(login_url, params=login_params,
                                  headers={"User-Agent": config.user_agent, "Content-Type": "application/json"})

    if login_response.status_code != 200:
        print("Login failed:", login_response.text)
        exit(1)

    login_data = login_response.json()
    if not login_data.get("valid", False):
        print("Invalid login credentials.")
        exit(1)

    # Extract required csrf_token from the login.py response
    csrf_token = login_data.get("token", "")
    return csrf_token

def list_instances_in_project(session: requests.Session, token: str ,projectName):
    result = set()
    project_metadata = loadProjectsMetaDataInfo(session, token,projectName)

    if 'instanceStructureSet' not in project_metadata["data"][0]:
        print("Error to find instanceStructureSet for project ", projectName,project_metadata["data"][0] )
        return result

    instances_dict = project_metadata["data"][0]["instanceStructureSet"]
    for entry in instances_dict:
        if 'i' not in entry or entry['i'].strip() == "":
            continue
        result.add(entry['i'])
        if 'c' in entry and entry['c'] is not None:
            container_list = entry['c']
            for container in container_list:
                result.add(container+"_"+entry['i'])
    return list(result)

def loadProjectsMetaDataInfo(session: requests.Session, token: str ,projectName):
    projectList = [{"projectName":projectName,"customerName": config.insightfinder_username}]
    form_data = {"projectList": json.dumps(projectList), "includeInstance": True}

    metadata_response = session.post(f"{config.insightfinder_url}/api/v1/loadProjectsMetaDataInfo",data=form_data, params={'tzOffset': -18000000},
                                     headers={"User-Agent": config.user_agent, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "X-CSRF-TOKEN": token},)
    response_json = metadata_response.json()
    return response_json

def get_component_names_from_metadata(metadata, project_instances_list):
    """Categorize hosts into matched and unmatched based on component regex"""
    instance_component_name_dict = {}
    
    for host in metadata:
        hostname = host['hostname']
        hostname = make_safe_instance_string(hostname)
        if hostname not in instance_component_name_dict and hostname in project_instances_list:
            component_type = match_component_type(hostname)
            
            # Extract jira_make tag value
            jira_make_value = None
            tags = host.get('tags', [])
            for tag in tags:
                if tag.get('tag') == 'jira_make':
                    jira_make_value = tag.get('value', '')
                    break
            
            # Append jira_make to component name if both exist
            if component_type and jira_make_value:
                component_type = f"{component_type}-{jira_make_value}"
            
            instance_component_name_dict[hostname] = component_type

    return instance_component_name_dict

def match_component_type(hostname):
    """Match hostname against regex patterns to determine component type"""
    for pattern, component_type in COMPONENT_REGEX_MAPPING:
        match = re.search(pattern, hostname, re.IGNORECASE)
        if match:
            return component_type
    
    # print(f"UNMATCHED: '{hostname}'")
    return None

def make_safe_instance_string(instance, device=''):
    """ make a safe instance name string, concatenated with device if appropriate """
    # strip underscores
    instance = UNDERSCORE.sub('.', instance)
    instance = COLONS.sub('-', instance)
    
    # remove leading special characters (hyphens, underscores, etc.)
    instance = re.sub(r'^[-_\W]+', '', instance)
    
    # if there's a device, concatenate it to the instance with an underscore
    if device:
        instance = '{}_{}'.format(make_safe_instance_string(device), instance)

    return instance

def save_to_file(logger, metadata, filename):
    """Save metadata to JSON file"""
    try:
        with open(filename, 'w') as f:
            json.dump(metadata, f, indent=2)
        logger.info(f"Metadata saved to {filename}")
        
        # Print summary
        tag_count = sum(len(host.get('tags', [])) for host in metadata)
        logger.info(f"Summary: {len(metadata)} hosts, {tag_count} total tags")
        
        return True
    except Exception as e:
        logger.error(f"Failed to save to file: {e}")
        return False
    
def save_component_files(logger, instance_component_name_dict):
    """Save instance component mapping to JSON file"""
    try:
        with open('instance_component.json', 'w') as f:
            json.dump(instance_component_name_dict, f, indent=2)
        logger.info(f"Components saved to instance_component.json")
        return True
    except Exception as e:
        logger.error(f"Failed to save component files: {e}")
        return False

def main():
    """Main function"""
    logger = setup_logging()
    
    # Connect to Zabbix
    zapi = connect_to_zabbix(logger)
    if not zapi:
        sys.exit(1)
    
    # Fetch metadata
    metadata = fetch_metadata(logger, zapi)
    if not metadata:
        sys.exit(1)
    
    # Save original metadata to file
    if not save_to_file(logger, metadata, OUTPUT_FILE):
        sys.exit(1)

    # Login to InsightFinder and get token
    logger.info("Logging in to InsightFinder...")
    session = requests.Session()
    token = login(session)

    # Get project instances list for IF
    project_instances_list = []
    project_instances_list = list_instances_in_project(session, token, config.insightfinder_project)
    logger.info(project_instances_list)

    # Match hostnames to component names
    logger.info("Matching hostnames to component names...")
    instance_component_name_dict = {}
    instance_component_name_dict = get_component_names_from_metadata(metadata, project_instances_list)

    # Save instance component mapping to a JSON file
    logger.info("Saving instance component mapping to JSON file...")
    if not save_component_files(logger, instance_component_name_dict):
        sys.exit(1)

if __name__ == "__main__":
    main()