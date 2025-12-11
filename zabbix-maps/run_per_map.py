#!/usr/bin/env python3
"""
Orchestrator script to process each Zabbix map individually and send to InsightFinder.
Avoids API size limits by sending one request per map.
No intermediate JSON files created per map - all processing in memory.
"""

import requests
import json
import sys
import logging
import time
import re
import regex
from pyzabbix import ZabbixAPI
import config

# Regular expressions for safe string conversion
UNDERSCORE = re.compile(r"\_+")
COLONS = re.compile(r"\:+")
LEFT_BRACE = re.compile(r"\[")
RIGHT_BRACE = re.compile(r"\]")
PERIOD = re.compile(r"\.")
COMMA = re.compile(r"\,")

# Component regex mapping loaded from config
COMPONENT_REGEX_MAPPING = config.component_regex_mapping

# Zabbix and InsightFinder configuration loaded from config.py
ZABBIX_URL = config.zabbix_url + '/api_jsonrpc.php'
INSIGHTFINDER_API_URL = config.insightfinder_url + '/api/v2/updaterelationdependency'

LOG_LEVEL = logging.INFO

def setup_logging():
    """Setup basic logging"""
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def make_safe_instance_string(instance, device=''):
    """Make a safe instance name string"""
    instance = UNDERSCORE.sub('.', instance)
    instance = COLONS.sub('-', instance)
    instance = re.sub(r'^[-_\W]+', '', instance)
    if device:
        instance = '{}_{}'.format(make_safe_instance_string(device), instance)
    return instance

def match_component_type(hostname):
    """Match hostname against regex patterns to determine component type"""
    for pattern, component_type in COMPONENT_REGEX_MAPPING:
        match = re.search(pattern, hostname, re.IGNORECASE)
        if match:
            return component_type
    return None

def get_zabbix_auth_token():
    """Authenticate to Zabbix API"""
    payload = {
        "jsonrpc": "2.0",
        "method": "user.login",
        "params": {
            "user": config.zabbix_user,
            "password": config.zabbix_password
        },
        "id": 1
    }
    response = requests.post(ZABBIX_URL, json=payload)
    return response.json()['result']

def fetch_all_maps(auth_token):
    """Fetch all maps from Zabbix"""
    params = {
        "output": "extend",
        "selectSelements": "extend",
        "selectLinks": "extend"
    }
    payload = {
        "jsonrpc": "2.0",
        "method": "map.get",
        "params": params,
        "auth": auth_token,
        "id": 2
    }
    response = requests.post(ZABBIX_URL, json=payload)
    resp_json = response.json()
    if 'result' in resp_json:
        return resp_json['result']
    else:
        raise Exception(f"Zabbix API error: {resp_json.get('error', 'Unknown error')}")

def fetch_host(auth_token, host_id):
    """Fetch host information from Zabbix"""
    payload = {
        "jsonrpc": "2.0",
        "method": "host.get",
        "params": {
            "output": ["hostid", "host", "name"],
            "hostids": [str(host_id)]
        },
        "auth": auth_token,
        "id": 3
    }
    response = requests.post(ZABBIX_URL, json=payload)
    resp_json = response.json()
    if 'result' in resp_json and resp_json['result']:
        return resp_json['result'][0]
    return None

def login_insightfinder(session):
    """Login to InsightFinder and get CSRF token"""
    login_url = f"{config.insightfinder_url}/api/v1/login-check"
    login_params = {
        "userName": config.insightfinder_username,
        "password": config.insightfinder_password
    }
    login_response = session.post(login_url, params=login_params,
                                  headers={"User-Agent": config.user_agent, "Content-Type": "application/json"})
    login_data = login_response.json()
    if not login_data.get("valid", False):
        raise Exception("Invalid InsightFinder login credentials")
    return login_data.get("token", "")

def get_project_instances(session, token, project_name):
    """Get list of instances in InsightFinder project"""
    project_list = [{"projectName": project_name, "customerName": config.insightfinder_username}]
    form_data = {"projectList": json.dumps(project_list), "includeInstance": True}
    
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
    
    result = set()
    if 'data' in response_json and response_json['data']:
        project_data = response_json['data'][0]
        if 'instanceStructureSet' in project_data:
            for entry in project_data['instanceStructureSet']:
                if 'i' in entry and entry['i'].strip():
                    result.add(entry['i'])
                    if 'c' in entry and entry['c'] is not None:
                        for container in entry['c']:
                            result.add(container + "_" + entry['i'])
    
    return list(result)

def fetch_zabbix_metadata(logger, zapi, project_instances_list):
    """Fetch metadata from Zabbix and create instance->component mapping"""
    logger.info("Fetching Zabbix host metadata...")
    
    # Get host groups
    host_groups_res = zapi.do_request('hostgroup.get', {'output': 'extend'})
    host_groups_ids = [item['groupid'] for item in host_groups_res['result']]
    
    # Get hosts
    hosts_res = zapi.do_request('host.get', {
        'output': ['name', 'hostid', 'host', 'status'],
        'groupids': host_groups_ids,
        'selectTags': 'extend'
    })
    
    # Create instance->component mapping
    instance_component_dict = {}
    
    for host in hosts_res['result']:
        hostname = make_safe_instance_string(host['host'])
        
        if hostname in project_instances_list:
            component_type = match_component_type(hostname)
            
            # Check for jira_make tag
            jira_make_value = None
            tags = host.get('tags', [])
            for tag in tags:
                if tag.get('tag') == 'jira_make':
                    jira_make_value = tag.get('value', '')
                    break
            
            # Append jira_make to component name if both exist
            if component_type and jira_make_value:
                component_type = f"{component_type}-{jira_make_value}"
            
            if component_type:
                instance_component_dict[hostname] = component_type
    
    logger.info(f"Created component mappings for {len(instance_component_dict)} instances")
    return instance_component_dict

def process_map_device_links(logger, zabbix_token, map_data):
    """Extract device links from a single map"""
    map_name = map_data.get('name', 'Unknown')
    map_id = map_data.get('sysmapid', 'unknown')
    
    if 'links' not in map_data or 'selements' not in map_data:
        logger.info(f"  Map '{map_name}' has no links or elements")
        return []
    
    if not map_data['links']:
        logger.info(f"  Map '{map_name}' has no links")
        return []
    
    # Build mapping from selementid to device name
    selement_name_map = {}
    for selement in map_data['selements']:
        if selement['elementtype'] == '0':  # Host
            host = fetch_host(zabbix_token, selement['elements'][0]['hostid'])
            if host:
                selement_name_map[selement['selementid']] = host.get('name', host.get('host', 'Unknown'))
            else:
                selement_name_map[selement['selementid']] = f"Host ID:{selement['elements'][0]['hostid']}"
        else:
            selement_name_map[selement['selementid']] = selement.get('label', f"ID:{selement['selementid']}")
    
    # Extract device links
    device_links = []
    for link in map_data['links']:
        name1 = selement_name_map.get(link['selementid1'], link['selementid1'])
        name2 = selement_name_map.get(link['selementid2'], link['selementid2'])
        
        safe_name1 = make_safe_instance_string(name1)
        safe_name2 = make_safe_instance_string(name2)
        
        device_links.append({
            "s": safe_name1,
            "t": safe_name2
        })
    
    logger.info(f"  Extracted {len(device_links)} device links from map '{map_name}'")
    return device_links

def create_component_links(device_links, instance_component_dict):
    """Transform device links to component links with deduplication"""
    component_links = []
    component_link_set = set()
    skipped_count = 0
    
    for link in device_links:
        source_device = link.get('s')
        target_device = link.get('t')
        
        source_component = instance_component_dict.get(source_device)
        target_component = instance_component_dict.get(target_device)
        
        if source_component and target_component:
            link_tuple = (source_component, target_component)
            
            if link_tuple not in component_link_set:
                component_link_set.add(link_tuple)
                component_links.append({
                    "s": source_component,
                    "t": target_component
                })
        else:
            skipped_count += 1
    
    return component_links, skipped_count

def send_component_links_to_insightfinder(logger, component_links, map_name):
    """Send component links to InsightFinder API"""
    if not component_links:
        logger.warning(f"  No component links to send for map '{map_name}'")
        return False
    
    # Transform to API format
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
    
    # Convert to JSON string
    component_relation_list_str = json.dumps(component_relation_list)
    
    # Create payload
    payload = {
        "systemDisplayName": config.insightfinder_system,
        "licenseKey": config.license_key,
        "userName": config.insightfinder_username,
        "dailyTimestamp": int(time.time() * 1000),
        "projectLevelAddRelationSetStr": component_relation_list_str
    }
    
    try:
        response = requests.post(
            INSIGHTFINDER_API_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            verify=False
        )
        
        if response.status_code == 200:
            logger.info(f"  ✓ Successfully sent {len(component_links)} component links for map '{map_name}'")
            return True
        else:
            logger.error(f"  ✗ Failed to send links for map '{map_name}': {response.status_code}")
            logger.error(f"    Response: {response.text}")
            return False
    except Exception as e:
        logger.error(f"  ✗ Error sending links for map '{map_name}': {e}")
        return False

def main():
    """Main orchestration function"""
    logger = setup_logging()
    
    logger.info("="*80)
    logger.info("Starting per-map Zabbix to InsightFinder workflow")
    logger.info("="*80)
    
    # Step 1: Connect to Zabbix
    logger.info("\n[1/6] Connecting to Zabbix...")
    zabbix_token = get_zabbix_auth_token()
    zapi = ZabbixAPI(server=config.zabbix_url, timeout=60)
    zapi.session.verify = False
    zapi.login(user=config.zabbix_user, password=config.zabbix_password)
    logger.info(f"  Connected to Zabbix API Version {zapi.api_version()}")
    
    # Step 2: Login to InsightFinder
    logger.info("\n[2/6] Logging into InsightFinder...")
    if_session = requests.Session()
    if_token = login_insightfinder(if_session)
    logger.info("  Logged into InsightFinder successfully")
    
    # Step 3: Get InsightFinder project instances
    logger.info(f"\n[3/6] Fetching instances from InsightFinder project '{config.insightfinder_project}'...")
    project_instances_list = get_project_instances(if_session, if_token, config.insightfinder_project)
    logger.info(f"  Found {len(project_instances_list)} instances in project")
    
    # Step 4: Fetch Zabbix metadata and create component mapping
    logger.info("\n[4/6] Creating instance->component mapping from Zabbix metadata...")
    instance_component_dict = fetch_zabbix_metadata(logger, zapi, project_instances_list)
    
    # Step 5: Fetch all maps
    logger.info("\n[5/6] Fetching all Zabbix maps...")
    maps = fetch_all_maps(zabbix_token)
    logger.info(f"  Found {len(maps)} maps in Zabbix")
    
    # Step 6: Process each map individually
    logger.info(f"\n[6/6] Processing and sending each map individually...")
    logger.info("="*80)
    
    total_maps = len(maps)
    maps_processed = 0
    maps_sent_successfully = 0
    maps_skipped = 0
    total_device_links = 0
    total_component_links = 0
    
    for map_idx, map_data in enumerate(maps, 1):
        map_name = map_data.get('name', f'Map {map_idx}')
        map_id = map_data.get('sysmapid', 'unknown')
        
        logger.info(f"\nMap {map_idx}/{total_maps}: '{map_name}' (ID: {map_id})")
        logger.info("-"*80)
        
        # Extract device links from this map
        device_links = process_map_device_links(logger, zabbix_token, map_data)
        
        if not device_links:
            logger.info("  Skipping - no device links in this map")
            maps_skipped += 1
            continue
        
        total_device_links += len(device_links)
        
        # Transform to component links
        component_links, skipped_count = create_component_links(device_links, instance_component_dict)
        
        if skipped_count > 0:
            logger.info(f"  Skipped {skipped_count} device links (missing component mapping)")
        
        total_component_links += len(component_links)
        
        # Send to InsightFinder
        if send_component_links_to_insightfinder(logger, component_links, map_name):
            maps_sent_successfully += 1
        
        maps_processed += 1
    
    # Final summary
    logger.info("\n" + "="*80)
    logger.info("FINAL SUMMARY")
    logger.info("="*80)
    logger.info(f"Total maps in Zabbix: {total_maps}")
    logger.info(f"Maps with device links: {maps_processed}")
    logger.info(f"Maps skipped (no links): {maps_skipped}")
    logger.info(f"Maps sent successfully: {maps_sent_successfully}")
    logger.info(f"Total device links extracted: {total_device_links}")
    logger.info(f"Total component links sent: {total_component_links}")
    logger.info("="*80)
    
    if maps_sent_successfully == 0:
        logger.error("No maps were sent successfully!")
        sys.exit(1)
    
    logger.info("\n✓ Workflow completed successfully!")

if __name__ == "__main__":
    main()
