#!/usr/bin/env python3

import requests
import sys
import getpass
import json
from urllib.parse import urljoin
import urllib3

# Disable SSL warnings when verify_certs is False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Import the working login function
from mimosa_login_working import mimosa_login

def explore_device_metrics(session, base_url, network_id="6078", verify_certs=False):
    """
    Explore available metrics for Mimosa devices
    """
    print(f"🔍 Exploring metrics for network {network_id}...")
    
    # First get the device list
    devices_url = urljoin(base_url, f'/{network_id}/devices/')
    
    try:
        response = session.get(devices_url, verify=verify_certs, timeout=30)
        if response.status_code != 200:
            print(f"❌ Failed to get devices: {response.status_code}")
            return
        
        devices_data = response.json()
        print(f"✅ Got devices data")
        
        # Examine the structure
        if 'content' in devices_data:
            devices = devices_data['content']
            total_devices = len(devices)
            print(f"📊 Found {total_devices} devices")
            
            if devices:
                # Show first few devices
                print(f"\n🔍 First 3 devices:")
                for i, device in enumerate(devices[:3]):
                    print(f"\nDevice {i+1}:")
                    device_id = device.get('id')
                    friendly_name = device.get('friendlyName', 'Unknown')
                    model = device.get('modelName', 'Unknown')
                    print(f"  ID: {device_id}")
                    print(f"  Name: {friendly_name}")
                    print(f"  Model: {model}")
                    
                    # Show all available keys for this device
                    print(f"  Available fields: {list(device.keys())}")
                
                # Try to get detailed metrics for the first device
                first_device = devices[0]
                device_id = first_device.get('id')
                if device_id:
                    print(f"\n🎯 Testing metrics endpoints for device {device_id}:")
                    
                    # Try various metric endpoints
                    metric_endpoints = [
                        f'/{network_id}/devices/{device_id}/',
                        f'/{network_id}/devices/{device_id}/stats/',
                        f'/{network_id}/devices/{device_id}/metrics/',
                        f'/{network_id}/devices/{device_id}/performance/',
                        f'/{network_id}/devices/{device_id}/status/',
                        f'/{network_id}/devices/{device_id}/health/',
                        f'/{network_id}/devices/{device_id}/radio/',
                        f'/{network_id}/devices/{device_id}/link/',
                        f'/{network_id}/devices/{device_id}/throughput/',
                        f'/{network_id}/devices/{device_id}/latency/',
                        f'/{network_id}/devices/{device_id}/snmp/',
                    ]
                    
                    working_endpoints = []
                    
                    for endpoint in metric_endpoints:
                        try:
                            url = urljoin(base_url, endpoint)
                            resp = session.get(url, verify=verify_certs, timeout=10)
                            
                            if resp.status_code == 200:
                                try:
                                    data = resp.json()
                                    working_endpoints.append((endpoint, data))
                                    print(f"    ✅ {endpoint} - Got JSON data")
                                    
                                    # Show structure of response
                                    if isinstance(data, dict):
                                        keys = list(data.keys())
                                        print(f"        Keys: {keys[:10]}{'...' if len(keys) > 10 else ''}")
                                    elif isinstance(data, list):
                                        print(f"        List with {len(data)} items")
                                    
                                except:
                                    print(f"    ✅ {endpoint} - Got non-JSON data")
                            else:
                                print(f"    ❌ {endpoint} - Status: {resp.status_code}")
                                
                        except Exception as e:
                            print(f"    ❌ {endpoint} - Error: {str(e)}")
                    
                    # Save detailed data for working endpoints
                    if working_endpoints:
                        print(f"\n💾 Saving detailed responses to files...")
                        for i, (endpoint, data) in enumerate(working_endpoints):
                            filename = f"mimosa_device_{device_id}_endpoint_{i+1}.json"
                            safe_filename = filename.replace('/', '_')
                            
                            with open(safe_filename, 'w') as f:
                                json.dump({
                                    'endpoint': endpoint,
                                    'device_id': device_id,
                                    'device_name': first_device.get('friendlyName', 'Unknown'),
                                    'data': data
                                }, f, indent=2)
                            print(f"    Saved: {safe_filename}")
        else:
            print(f"⚠️ Unexpected devices data structure: {list(devices_data.keys())}")
            
    except Exception as e:
        print(f"❌ Error exploring devices: {str(e)}")


def test_network_level_metrics(session, base_url, network_id="6078", verify_certs=False):
    """
    Test network-level metric endpoints
    """
    print(f"\n🌐 Testing network-level metrics for network {network_id}...")
    
    network_endpoints = [
        f'/{network_id}/deviceCount/',
        f'/{network_id}/devices/',
        f'/{network_id}/summary/',
        f'/{network_id}/stats/',
        f'/{network_id}/performance/',
        f'/{network_id}/health/',
        f'/{network_id}/alerts/',
        f'/{network_id}/topology/',
        f'/{network_id}/reports/',
        f'/{network_id}/analytics/',
        f'/{network_id}/metrics/',
    ]
    
    working_endpoints = []
    
    for endpoint in network_endpoints:
        try:
            url = urljoin(base_url, endpoint)
            resp = session.get(url, verify=verify_certs, timeout=10)
            
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    working_endpoints.append((endpoint, data))
                    print(f"  ✅ {endpoint} - Got JSON data")
                    
                    # Show brief structure
                    if isinstance(data, dict):
                        keys = list(data.keys())
                        print(f"      Keys: {keys[:5]}{'...' if len(keys) > 5 else ''}")
                    elif isinstance(data, list):
                        print(f"      List with {len(data)} items")
                        
                except:
                    print(f"  ✅ {endpoint} - Got non-JSON data")
            else:
                print(f"  ❌ {endpoint} - Status: {resp.status_code}")
                
        except Exception as e:
            print(f"  ❌ {endpoint} - Error: {str(e)}")
    
    # Save network-level data
    if working_endpoints:
        print(f"\n💾 Saving network-level responses...")
        for i, (endpoint, data) in enumerate(working_endpoints):
            filename = f"mimosa_network_{network_id}_endpoint_{i+1}.json"
            safe_filename = filename.replace('/', '_')
            
            with open(safe_filename, 'w') as f:
                json.dump({
                    'endpoint': endpoint,
                    'network_id': network_id,
                    'data': data
                }, f, indent=2)
            print(f"    Saved: {safe_filename}")


def main():
    """
    Main function to explore Mimosa metrics
    """
    if len(sys.argv) >= 4:
        base_url = sys.argv[1]
        username = sys.argv[2]
        password = sys.argv[3]
        verify_certs = sys.argv[4].lower() == 'true' if len(sys.argv) > 4 else False
    else:
        print("Mimosa Metrics Explorer")
        print("-" * 25)
        base_url = input("Base URL (e.g., https://cloud.mimosa.co): ").strip()
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        verify_input = input("Verify SSL certificates? (y/N): ").strip().lower()
        verify_certs = verify_input in ['y', 'yes', 'true']
    
    try:
        # Login
        print(f"\n🔐 Logging in to {base_url}...")
        session = mimosa_login(base_url, username, password, verify_certs)
        
        # Test network-level metrics
        test_network_level_metrics(session, base_url, "6078", verify_certs)
        
        # Explore device metrics
        explore_device_metrics(session, base_url, "6078", verify_certs)
        
        print(f"\n✅ Metrics exploration completed!")
        print(f"📁 Check the generated JSON files for detailed API responses.")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
