#!/usr/bin/env python3
"""
ServiceNow Ticket Creation Script

This script creates incident tickets in ServiceNow using the REST API.
Configuration is loaded from config.yaml file.
"""

import requests
import yaml
import json
import sys
import random
from datetime import datetime
from typing import Dict, Any


class ServiceNowClient:
    """Client for interacting with ServiceNow API"""
    
    def __init__(self, instance_url: str, username: str, password: str):
        """
        Initialize ServiceNow client
        
        Args:
            instance_url: ServiceNow instance URL
            username: ServiceNow username
            password: ServiceNow password
        """
        self.instance_url = instance_url.rstrip('/')
        self.username = username
        self.password = password
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def create_incident(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create an incident ticket in ServiceNow
        
        Args:
            payload: Dictionary containing incident details
            
        Returns:
            Dictionary containing the created incident details
        """
        url = f"{self.instance_url}/api/now/table/incident"
        
        try:
            response = requests.post(
                url,
                auth=(self.username, self.password),
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            return {
                'success': True,
                'data': result.get('result', {}),
                'status_code': response.status_code
            }
            
        except requests.exceptions.HTTPError as e:
            return {
                'success': False,
                'error': f"HTTP Error: {e}",
                'status_code': response.status_code,
                'response': response.text
            }
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f"Request Error: {e}"
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Unexpected Error: {e}"
            }


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        Dictionary containing configuration
    """
    try:
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
            return config
    except FileNotFoundError:
        print(f"Error: Configuration file '{config_path}' not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        sys.exit(1)


def prepare_ticket_payload(ticket_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare the ticket payload from configuration
    
    Args:
        ticket_config: Ticket configuration from config.yaml
        
    Returns:
        Dictionary containing the ticket payload
    """
    payload = {}
    
    # Required fields
    if 'short_description' in ticket_config:
        short_desc = ticket_config['short_description']
        
        # Replace random placeholders with actual random values
        # Format: {random:min-max:decimals}
        import re
        
        # Find all random placeholders
        random_pattern = r'\{random:([\d.]+)-([\d.]+):(\d+)\}'
        matches = re.findall(random_pattern, short_desc)
        
        for match in matches:
            min_val, max_val, decimals = float(match[0]), float(match[1]), int(match[2])
            random_value = random.uniform(min_val, max_val)
            placeholder = f"{{random:{match[0]}-{match[1]}:{match[2]}}}"
            short_desc = short_desc.replace(placeholder, f"{random_value:.{decimals}f}", 1)
        
        payload['short_description'] = short_desc
    
    # Optional fields
    optional_fields = [
        'description',
        'urgency',
        'impact',
        'category',
        'assignment_group',
        'assigned_to',
        'caller_id',
        'contact_type',
        'subcategory',
        'cmdb_ci',
        'work_notes',
        'comments',
        'location',
        'business_service',
        'priority',
        'state',
        'opened_at'
    ]
    
    for field in optional_fields:
        if field in ticket_config and ticket_config[field]:
            payload[field] = ticket_config[field]
    
    return payload


def print_ticket_details(ticket_data: Dict[str, Any]):
    """
    Print ticket details in a readable format
    
    Args:
        ticket_data: Ticket data returned from ServiceNow
    """
    print("\n" + "="*60)
    print("TICKET CREATED SUCCESSFULLY")
    print("="*60)
    print(f"Ticket Number: {ticket_data.get('number', 'N/A')}")
    print(f"Sys ID: {ticket_data.get('sys_id', 'N/A')}")
    print(f"Short Description: {ticket_data.get('short_description', 'N/A')}")
    print(f"State: {ticket_data.get('state', 'N/A')}")
    print(f"Priority: {ticket_data.get('priority', 'N/A')}")
    print(f"Created: {ticket_data.get('sys_created_on', 'N/A')}")
    print("="*60 + "\n")


def main():
    """Main function to create ServiceNow ticket"""
    
    print("ServiceNow Ticket Creation Script")
    print("-" * 60)
    
    # Load configuration
    print("Loading configuration from config.yaml...")
    config = load_config()
    
    # Extract ServiceNow credentials
    snow_config = config.get('servicenow', {})
    instance_url = snow_config.get('instance_url')
    username = snow_config.get('username')
    password = snow_config.get('password')
    
    if not all([instance_url, username, password]):
        print("Error: ServiceNow credentials are incomplete in config.yaml")
        sys.exit(1)
    
    # Extract ticket configuration
    ticket_config = config.get('ticket', {})
    if not ticket_config.get('short_description'):
        print("Error: 'short_description' is required in ticket configuration")
        sys.exit(1)
    
    # Initialize ServiceNow client
    print(f"Connecting to ServiceNow instance: {instance_url}")
    client = ServiceNowClient(instance_url, username, password)
    
    # Prepare ticket payload
    payload = prepare_ticket_payload(ticket_config)
    print(f"\nTicket Payload:")
    print(json.dumps(payload, indent=2))
    
    # Create ticket
    print("\nCreating incident ticket...")
    result = client.create_incident(payload)
    
    # Handle result
    if result['success']:
        ticket_data = result['data']
        print_ticket_details(ticket_data)
        
        # Generate ticket URL
        ticket_number = ticket_data.get('sys_id')
        if ticket_number:
            ticket_url = f"{instance_url}/now/nav/ui/classic/params/target/incident.do?sys_id={ticket_number}"
            print(f"Ticket URL: {ticket_url}\n")
        
        return 0
    else:
        print("\n" + "="*60)
        print("TICKET CREATION FAILED")
        print("="*60)
        print(f"Error: {result.get('error', 'Unknown error')}")
        if 'status_code' in result:
            print(f"Status Code: {result['status_code']}")
        if 'response' in result:
            print(f"Response: {result['response']}")
        print("="*60 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
