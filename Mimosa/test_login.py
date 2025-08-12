#!/usr/bin/env python3

import requests
import sys
import getpass
from urllib.parse import urljoin

def test_mimosa_login(base_url, username, password, verify_certs=False):
    """
    Test login to Mimosa device using the provided credentials
    """
    # Try different login URLs that might work
    login_urls = [
        urljoin(base_url, '/j_spring_security_check'),
        urljoin(base_url, '/login/j_spring_security_check'),
        urljoin(base_url, '/app/login/j_spring_security_check'),
        urljoin(base_url, '/api/login'),
        urljoin(base_url, '/app/welcome.html#/login/j_spring_security_check')
    ]
    
    # Prepare the form data
    login_data = {
        'j_username': username,
        'j_password': password
    }
    
    # Create a session to maintain cookies
    session = requests.Session()
    
    for login_url in login_urls:
        try:
            print(f"Trying login URL: {login_url}")
            print(f"Username: {username}")
            print(f"Password: {'*' * len(password)}")
            print("-" * 50)
            
            # Make the login request
            response = session.post(
                login_url,
                data=login_data,  # Using form data like in curl
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
                },
                verify=verify_certs,
                timeout=30,
                allow_redirects=True
            )
            
            print(f"Response Status Code: {response.status_code}")
            print(f"Response Headers:")
            for header, value in response.headers.items():
                print(f"  {header}: {value}")
            
            print(f"\nResponse Cookies:")
            for cookie in session.cookies:
                print(f"  {cookie.name}: {cookie.value}")
            
            print(f"\nResponse Content (first 500 chars):")
            print(response.text[:500])
            
            # Save cookies to file (like curl -c cookies.txt)
            with open('cookies.txt', 'w') as f:
                for cookie in session.cookies:
                    f.write(f"{cookie.name}\t{cookie.value}\n")
            
            # Check if login was successful
            if response.status_code == 200:
                if 'error' in response.text.lower() or 'invalid' in response.text.lower():
                    print(f"\n❌ Login failed for {login_url} (error found in response)")
                else:
                    print(f"\n✅ Login successful with {login_url}!")
                    return True, session
            elif response.status_code == 302:
                print(f"\n✅ Login successful with {login_url} (redirect response)!")
                return True, session
            else:
                print(f"\n❌ Login failed for {login_url} with status code: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            print(f"\n❌ Request failed for {login_url}: {str(e)}")
            continue
        
        print("\n" + "="*60 + "\n")
    
    print("❌ All login attempts failed")
    return False, None


def discover_mimosa_networks(session, base_url, verify_certs=False):
    """
    Try to discover available networks/organizations and their IDs
    """
    print("\n" + "="*50)
    print("Discovering Mimosa Networks:")
    print("="*50)
    
    # Common endpoints that might reveal network information
    discovery_endpoints = [
        '/api/networks',
        '/api/user/networks',
        '/api/organizations',
        '/api/user/organizations',
        '/api/user/profile',
        '/api/dashboard',
        '/user/networks',
        '/networks',
        '/organizations'
    ]
    
    networks_found = []
    
    for endpoint in discovery_endpoints:
        try:
            url = urljoin(base_url, endpoint)
            print(f"\nTrying: {url}")
            
            response = session.get(url, verify=verify_certs, timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"✅ Got JSON data from {endpoint}")
                    print(f"Data structure: {type(data)}")
                    
                    if isinstance(data, dict):
                        print(f"Keys: {list(data.keys())}")
                        # Look for network/organization IDs
                        for key, value in data.items():
                            if 'network' in key.lower() or 'org' in key.lower() or 'id' in key.lower():
                                print(f"  {key}: {value}")
                                if isinstance(value, (list, dict)):
                                    networks_found.append((key, value))
                    elif isinstance(data, list):
                        print(f"List with {len(data)} items")
                        if data:
                            print(f"First item: {data[0]}")
                            networks_found.append(('networks_list', data))
                    
                    # Print first 300 chars of response for inspection
                    print(f"Response preview: {str(data)[:300]}...")
                    
                except json.JSONDecodeError:
                    print(f"Non-JSON response: {response.text[:200]}...")
            else:
                print(f"❌ {response.status_code} - {response.reason}")
                
        except Exception as e:
            print(f"Error testing {endpoint}: {str(e)}")
    
    return networks_found


def test_mimosa_api_with_network_id(session, base_url, network_id=None, verify_certs=False):
    """
    Test Mimosa API endpoints with a specific network ID
    """
    print("\n" + "="*50)
    print(f"Testing Mimosa API with Network ID: {network_id or '6078 (default)'}")
    print("="*50)
    
    # Use provided network_id or default to 6078
    net_id = network_id or '6078'
    
    # Test various API endpoints with the network ID
    api_endpoints = [
        f'/{net_id}/deviceCount/',
        f'/{net_id}/devices/',
        f'/{net_id}/networks/',
        f'/{net_id}/stats/',
        f'/{net_id}/metrics/',
        f'/{net_id}/dashboard/',
        f'/api/{net_id}/devices',
        f'/api/{net_id}/stats',
        f'/api/networks/{net_id}/devices',
        f'/api/networks/{net_id}/stats'
    ]
    
    successful_endpoints = []
    
    for endpoint in api_endpoints:
        try:
            url = urljoin(base_url, endpoint)
            print(f"\nTesting: {url}")
            
            response = session.get(url, verify=verify_certs, timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                print(f"✅ SUCCESS! Content length: {len(response.text)} chars")
                
                # Try to parse as JSON
                try:
                    data = response.json()
                    print(f"JSON Response:")
                    print(f"  Type: {type(data)}")
                    if isinstance(data, dict):
                        print(f"  Keys: {list(data.keys())}")
                    elif isinstance(data, list):
                        print(f"  List length: {len(data)}")
                    
                    # Print formatted JSON (first 500 chars)
                    json_str = json.dumps(data, indent=2)
                    print(f"  Data preview:\n{json_str[:500]}{'...' if len(json_str) > 500 else ''}")
                    
                    successful_endpoints.append((endpoint, data))
                    
                except json.JSONDecodeError:
                    print(f"  Non-JSON response: {response.text[:200]}...")
                    successful_endpoints.append((endpoint, response.text))
                    
            elif response.status_code == 404:
                print(f"❌ Not Found")
            elif response.status_code == 403:
                print(f"❌ Forbidden - might need different permissions")
            elif response.status_code == 401:
                print(f"❌ Unauthorized - session might have expired")
            else:
                print(f"❌ {response.status_code} - {response.reason}")
                print(f"  Response: {response.text[:100]}...")
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
    
    print(f"\n🎯 SUMMARY: Found {len(successful_endpoints)} working endpoints")
    for endpoint, _ in successful_endpoints:
        print(f"  ✅ {endpoint}")
    
    return successful_endpoints
    """
    Test an authenticated request to verify the session is working
    """
    if not session:
        print("No valid session to test with")
        return
    
    # Try to access a protected endpoint
    test_urls = [
        '/6078/deviceCount/',
        '/api/stats',
        '/api/status',
        '/api/info',
        '/app/dashboard'
    ]
    
    print("\n" + "="*50)
    print("Testing authenticated requests:")
    print("="*50)
    
    for endpoint in test_urls:
        try:
            url = urljoin(base_url, endpoint)
            print(f"\nTesting: {url}")
            
            response = session.get(
                url,
                verify=verify_certs,
                timeout=10
            )
            
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                print(f"Content length: {len(response.text)} chars")
                if response.headers.get('content-type', '').startswith('application/json'):
                    try:
                        import json
                        data = response.json()
                        print(f"JSON keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                        print(f"JSON data: {json.dumps(data, indent=2)}")
                    except:
                        print("Response is not valid JSON")
                        print(f"Response content (first 200 chars): {response.text[:200]}")
                else:
                    print(f"Response content (first 200 chars): {response.text[:200]}")
            else:
                print(f"Error: {response.status_code} - {response.reason}")
                print(f"Response content (first 200 chars): {response.text[:200]}")
                
        except Exception as e:
            print(f"Failed to test {endpoint}: {str(e)}")


def main():
    """
    Main function to run the login test
    """
    # Option 1: Interactive mode if no arguments
    if len(sys.argv) < 4:
        print("Mimosa Login Test Script")
        print("=" * 30)
        print("Enter credentials (or use: python test_login.py <base_url> <username> <password> [verify_certs])")
        print()
        
        try:
            base_url = input("Base URL (e.g., https://cloud.mimosa.co): ").strip()
            username = input("Username: ").strip()
            import getpass
            password = getpass.getpass("Password: ")
            verify_input = input("Verify SSL certificates? (y/N): ").strip().lower()
            verify_certs = verify_input in ['y', 'yes', 'true']
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            sys.exit(0)
        except Exception as e:
            print(f"Error reading input: {e}")
            sys.exit(1)
    else:
        # Command line arguments
        base_url = sys.argv[1]
        username = sys.argv[2]
        password = sys.argv[3]
        verify_certs = sys.argv[4].lower() == 'true' if len(sys.argv) > 4 else False
    
    # Validate inputs
    if not base_url or not username or not password:
        print("Error: All fields (base_url, username, password) are required")
        sys.exit(1)
    
    print("Mimosa Login Test Script")
    print("=" * 30)
    
    # Test login
    success, session = test_mimosa_login(base_url, username, password, verify_certs)
    
    if success and session:
        # Test some authenticated requests
        test_authenticated_request(session, base_url, verify_certs)
    
    print("\nTest completed!")


if __name__ == "__main__":
    main()
