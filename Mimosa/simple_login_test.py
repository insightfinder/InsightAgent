#!/usr/bin/env python3

import requests
import sys

def simple_mimosa_login_test():
    """
    Simple test that mirrors the curl command exactly
    """
    # Default values - modify these or pass as command line arguments
    base_url = "https://cloud.mimosa.co"
    username = "user"  # Change this
    password = "password"  # Change this
    
    # Allow command line override
    if len(sys.argv) >= 4:
        base_url = sys.argv[1]
        username = sys.argv[2]
        password = sys.argv[3]
    
    # The exact URL from your curl command
    login_url = f"{base_url}/app/welcome.html#/login/j_spring_security_check"
    
    print(f"Testing login to: {login_url}")
    print(f"Username: {username}")
    print("-" * 40)
    
    # Prepare session and data exactly like curl
    session = requests.Session()
    
    # Form data exactly as in curl
    form_data = {
        'j_username': username,
        'j_password': password
    }
    
    try:
        # Make request with same parameters as curl
        response = session.post(
            login_url,
            data=form_data,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            verify=False,  # -k flag in curl
            allow_redirects=True
        )
        
        # Display response like curl -i
        print(f"HTTP/{response.raw.version // 10}.{response.raw.version % 10} {response.status_code} {response.reason}")
        
        # Print headers
        for header, value in response.headers.items():
            print(f"{header}: {value}")
        
        print()  # Empty line before body
        
        # Print response body (first 1000 chars)
        print(response.text[:1000])
        if len(response.text) > 1000:
            print(f"\n... (truncated, total length: {len(response.text)} chars)")
        
        # Save cookies to file like curl -c
        with open('cookies.txt', 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for cookie in session.cookies:
                f.write(f"{cookie.domain}\tTRUE\t{cookie.path}\t{'TRUE' if cookie.secure else 'FALSE'}\t0\t{cookie.name}\t{cookie.value}\n")
        
        print(f"\nCookies saved to cookies.txt ({len(session.cookies)} cookies)")
        
        # Simple success check
        if response.status_code in [200, 302]:
            print("✅ Request completed successfully")
        else:
            print(f"❌ Request failed with status {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] in ['-h', '--help']:
        print("Usage: python simple_login_test.py [base_url] [username] [password]")
        print("Example: python simple_login_test.py https://cloud.mimosa.co myuser mypass")
        print("\nIf no arguments provided, uses defaults from script")
        sys.exit(0)
    
    simple_mimosa_login_test()
