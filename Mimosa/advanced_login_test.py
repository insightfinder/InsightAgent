#!/usr/bin/env python3

import requests
import sys
import getpass
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

def get_csrf_token(session, base_url, verify_certs=False):
    """Get CSRF token from login page if required"""
    try:
        login_page_url = urljoin(base_url, '/app/welcome.html')
        response = session.get(login_page_url, verify=verify_certs)
        
        if response.status_code == 200:
            # Try to find CSRF token in the HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for common CSRF token patterns
            csrf_input = soup.find('input', {'name': '_token'}) or \
                        soup.find('input', {'name': 'csrf_token'}) or \
                        soup.find('input', {'name': '_csrf'}) or \
                        soup.find('input', {'name': 'authenticity_token'})
            
            if csrf_input:
                return csrf_input.get('value')
                
            # Look for CSRF token in meta tags
            csrf_meta = soup.find('meta', {'name': 'csrf-token'}) or \
                       soup.find('meta', {'name': '_token'})
            
            if csrf_meta:
                return csrf_meta.get('content')
                
            # Look for CSRF token in JavaScript variables
            csrf_match = re.search(r'_token["\']?\s*[:=]\s*["\']([^"\']+)["\']', response.text) or \
                        re.search(r'csrf["\']?\s*[:=]\s*["\']([^"\']+)["\']', response.text, re.IGNORECASE)
            
            if csrf_match:
                return csrf_match.group(1)
        
        return None
        
    except Exception as e:
        print(f"Error getting CSRF token: {e}")
        return None


def test_spring_security_login(base_url, username, password, verify_certs=False):
    """
    Test Spring Security login with proper session handling
    """
    session = requests.Session()
    
    try:
        print(f"Testing Spring Security login to: {base_url}")
        print(f"Username: {username}")
        print(f"Password: {'*' * len(password)}")
        print("-" * 50)
        
        # Step 1: Get the login page to establish session
        print("Step 1: Getting login page...")
        login_page_url = urljoin(base_url, '/app/welcome.html')
        page_response = session.get(login_page_url, verify=verify_certs)
        print(f"Login page status: {page_response.status_code}")
        
        # Step 2: Try to get CSRF token
        print("Step 2: Looking for CSRF token...")
        csrf_token = get_csrf_token(session, base_url, verify_certs)
        if csrf_token:
            print(f"Found CSRF token: {csrf_token[:20]}...")
        else:
            print("No CSRF token found")
        
        # Step 3: Prepare login data
        login_data = {
            'j_username': username,
            'j_password': password
        }
        
        if csrf_token:
            login_data['_token'] = csrf_token
            # Try other common CSRF parameter names
            login_data['csrf_token'] = csrf_token
            login_data['_csrf'] = csrf_token
        
        # Step 4: Try login with different URLs
        login_endpoints = [
            '/login/j_spring_security_check',
            '/j_spring_security_check',
            '/app/j_spring_security_check'
        ]
        
        for endpoint in login_endpoints:
            login_url = urljoin(base_url, endpoint)
            print(f"\nStep 3: Attempting login to {login_url}")
            
            # Make the login request
            response = session.post(
                login_url,
                data=login_data,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                    'Referer': login_page_url
                },
                verify=verify_certs,
                timeout=30,
                allow_redirects=False  # Don't follow redirects to see what happens
            )
            
            print(f"Response Status Code: {response.status_code}")
            print(f"Response Headers:")
            for header, value in response.headers.items():
                print(f"  {header}: {value}")
            
            print(f"\nResponse Cookies:")
            for cookie in session.cookies:
                print(f"  {cookie.name}: {cookie.value}")
            
            # Check for success indicators
            if response.status_code in [200, 302, 303]:
                if response.status_code == 302 or response.status_code == 303:
                    location = response.headers.get('Location', '')
                    print(f"\nRedirect location: {location}")
                    
                    if 'error' not in location.lower() and 'login' not in location.lower():
                        print(f"✅ Login successful! Redirected to: {location}")
                        return True, session
                    else:
                        print(f"❌ Login failed - redirected to error/login page")
                
                elif response.status_code == 200:
                    # Check response content for success indicators
                    content_lower = response.text.lower()
                    if any(indicator in content_lower for indicator in ['dashboard', 'welcome', 'logout', 'profile']):
                        print("✅ Login successful! Found success indicators in response")
                        return True, session
                    elif any(error in content_lower for error in ['error', 'invalid', 'authentication failed', 'bad credentials']):
                        print("❌ Login failed - found error indicators in response")
                    else:
                        print("? Login status unclear from response content")
                        print(f"Response content (first 200 chars): {response.text[:200]}")
            else:
                print(f"❌ Login failed with status code: {response.status_code}")
        
        return False, None
        
    except Exception as e:
        print(f"❌ Error during login: {str(e)}")
        return False, None


def test_curl_method(base_url, username, password, verify_certs=False):
    """
    Test the exact method from your curl command
    """
    session = requests.Session()
    
    print(f"Testing CURL method to: {base_url}")
    print(f"Username: {username}")
    print(f"Password: {'*' * len(password)}")
    print("-" * 50)
    
    # The exact URL from your curl command (without the fragment)
    login_url = urljoin(base_url, '/app/welcome.html')  # Remove fragment part
    
    # Try to GET the page first (like curl does implicitly)
    print("Step 1: GET the welcome page...")
    get_response = session.get(login_url, verify=verify_certs)
    print(f"GET response: {get_response.status_code}")
    
    # Now try POST to the Spring Security endpoint
    spring_url = urljoin(base_url, '/login/j_spring_security_check')
    print(f"Step 2: POST to {spring_url}")
    
    form_data = {
        'j_username': username,
        'j_password': password
    }
    
    try:
        response = session.post(
            spring_url,
            data=form_data,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'curl/7.68.0'  # Mimic curl user agent
            },
            verify=verify_certs,
            timeout=30,
            allow_redirects=True
        )
        
        print(f"POST Response Status Code: {response.status_code}")
        print(f"Final URL after redirects: {response.url}")
        
        # Save cookies like curl -c
        with open('cookies.txt', 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for cookie in session.cookies:
                f.write(f"{cookie.domain}\t{'TRUE' if cookie.domain.startswith('.') else 'FALSE'}\t{cookie.path}\t{'TRUE' if cookie.secure else 'FALSE'}\t0\t{cookie.name}\t{cookie.value}\n")
        
        print(f"Cookies saved to cookies.txt")
        
        # Check if we're on a success page
        if 'dashboard' in response.url or 'home' in response.url or response.status_code == 200:
            print("✅ Login appears successful!")
            return True, session
        else:
            print("❌ Login may have failed")
            print(f"Response content (first 300 chars):\n{response.text[:300]}")
            return False, session
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False, None


def main():
    """
    Main function with both approaches
    """
    # Get credentials
    if len(sys.argv) < 4:
        print("Mimosa Login Test Script (Advanced)")
        print("=" * 40)
        print("Enter credentials:")
        print()
        
        try:
            base_url = input("Base URL (e.g., https://cloud.mimosa.co): ").strip()
            username = input("Username: ").strip()
            password = getpass.getpass("Password: ")
            verify_input = input("Verify SSL certificates? (y/N): ").strip().lower()
            verify_certs = verify_input in ['y', 'yes', 'true']
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            sys.exit(0)
    else:
        base_url = sys.argv[1]
        username = sys.argv[2]
        password = sys.argv[3]
        verify_certs = sys.argv[4].lower() == 'true' if len(sys.argv) > 4 else False
    
    print("\n" + "="*60)
    print("METHOD 1: Spring Security approach")
    print("="*60)
    success1, session1 = test_spring_security_login(base_url, username, password, verify_certs)
    
    print("\n" + "="*60)
    print("METHOD 2: Direct CURL approach")
    print("="*60)
    success2, session2 = test_curl_method(base_url, username, password, verify_certs)
    
    print(f"\nSUMMARY:")
    print(f"Spring Security method: {'✅ Success' if success1 else '❌ Failed'}")
    print(f"CURL method: {'✅ Success' if success2 else '❌ Failed'}")


if __name__ == "__main__":
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("Warning: BeautifulSoup not available. Installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4"])
        from bs4 import BeautifulSoup
    
    main()
