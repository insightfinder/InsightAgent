#!/usr/bin/env python3

import requests
import sys
import getpass
from urllib.parse import urljoin

def mimosa_login(base_url, username, password, verify_certs=False):
    """
    Login to Mimosa cloud and return authenticated session
    
    Args:
        base_url (str): Base URL like 'https://cloud.mimosa.co'
        username (str): Username for login
        password (str): Password for login
        verify_certs (bool): Whether to verify SSL certificates
    
    Returns:
        requests.Session: Authenticated session object
    
    Raises:
        Exception: If login fails
    """
    session = requests.Session()
    
    try:
        # Step 1: Get the welcome page to establish session
        welcome_url = urljoin(base_url, '/app/welcome.html')
        welcome_response = session.get(welcome_url, verify=verify_certs, timeout=30)
        welcome_response.raise_for_status()
        
        # Step 2: Login using Spring Security endpoint
        login_url = urljoin(base_url, '/login/j_spring_security_check')
        
        login_data = {
            'j_username': username,
            'j_password': password
        }
        
        response = session.post(
            login_url,
            data=login_data,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                'Referer': welcome_url
            },
            verify=verify_certs,
            timeout=30,
            allow_redirects=False
        )
        
        # Check if login was successful
        if response.status_code in [302, 303]:
            location = response.headers.get('Location', '')
            if 'app/index.html' in location and 'error' not in location.lower():
                print(f"✅ Login successful! Redirected to: {location}")
                return session
            else:
                raise Exception(f"Login failed: redirected to {location}")
        elif response.status_code == 200:
            print("✅ Login successful!")
            return session
        else:
            raise Exception(f"Login failed with status code: {response.status_code}")
            
    except Exception as e:
        raise Exception(f"Failed to login to Mimosa: {str(e)}")


def test_authenticated_request(session, base_url, endpoint='/api/stats', verify_certs=False):
    """
    Test an authenticated request to verify the session works
    
    Args:
        session: Authenticated session from mimosa_login()
        base_url: Base URL of Mimosa cloud
        endpoint: API endpoint to test
        verify_certs: Whether to verify SSL certificates
    
    Returns:
        dict: Response data if successful, None if failed
    """
    try:
        url = urljoin(base_url, endpoint)
        response = session.get(url, verify=verify_certs, timeout=30)
        
        print(f"Testing {url}: Status {response.status_code}")
        
        if response.status_code == 200:
            try:
                return response.json()
            except:
                return response.text
        else:
            print(f"Request failed: {response.status_code} - {response.reason}")
            return None
            
    except Exception as e:
        print(f"Error testing endpoint {endpoint}: {str(e)}")
        return None


def main():
    """Demo usage of the login function"""
    if len(sys.argv) >= 4:
        base_url = sys.argv[1]
        username = sys.argv[2]
        password = sys.argv[3]
        verify_certs = sys.argv[4].lower() == 'true' if len(sys.argv) > 4 else False
    else:
        print("Mimosa Login Demo")
        print("-" * 20)
        base_url = input("Base URL (e.g., https://cloud.mimosa.co): ").strip()
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        verify_input = input("Verify SSL certificates? (y/N): ").strip().lower()
        verify_certs = verify_input in ['y', 'yes', 'true']
    
    try:
        # Login
        print(f"\nLogging in to {base_url}...")
        session = mimosa_login(base_url, username, password, verify_certs)
        
        # Test some endpoints
        print("\nTesting authenticated endpoints:")
        endpoints = ['/api/stats', '/api/status', '/api/info', '/api/devices']
        
        for endpoint in endpoints:
            result = test_authenticated_request(session, base_url, endpoint, verify_certs)
            if result:
                print(f"  ✅ {endpoint} - Got data")
            else:
                print(f"  ❌ {endpoint} - No data or error")
        
        print(f"\n✅ Session is working! You can now use it for API calls.")
        
        # Save session cookies for reference
        with open('working_session_cookies.txt', 'w') as f:
            f.write("# Working Mimosa session cookies\n")
            for cookie in session.cookies:
                f.write(f"{cookie.name}={cookie.value}\n")
        
        print("Session cookies saved to 'working_session_cookies.txt'")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
