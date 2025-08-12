#!/usr/bin/env python3
import requests
import json
from urllib.parse import urljoin
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_device_structure():
    session = requests.Session()
    mimosa_uri = 'https://cloud.mimosa.co'
    username = 'maoyu@insightfinder.com'
    password = 'jtd1wyw3mju-bqc!FHX'

    try:
        # Login
        welcome_url = urljoin(mimosa_uri, '/app/welcome.html')
        session.get(welcome_url, verify=False, timeout=30)

        login_url = urljoin(mimosa_uri, '/login/j_spring_security_check')
        login_data = {'j_username': username, 'j_password': password}
        session.post(login_url, data=login_data, verify=False, timeout=30, allow_redirects=False)

        # Get one device
        devices_url = urljoin(mimosa_uri, '/6078/devices/')
        params = {'pageNumber': 0, 'pageSize': 1}
        response = session.get(devices_url, params=params, verify=False, timeout=30)
        data = response.json()

        if 'content' in data and len(data['content']) > 0:
            device = data['content'][0]
            print('Device keys:', sorted(list(device.keys())))
            print('\nSample device data:')
            print(json.dumps(device, indent=2))
            
            # Look for numeric fields that could be metrics
            numeric_fields = []
            for key, value in device.items():
                if isinstance(value, (int, float)) and key not in ['id']:
                    numeric_fields.append(key)
            
            print(f'\nNumeric fields (potential metrics): {sorted(numeric_fields)}')
            
        else:
            print('No devices found')
    except Exception as e:
        print(f'Error: {e}')

if __name__ == '__main__':
    get_device_structure()
