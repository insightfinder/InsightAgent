
import json
import requests
import sqlite3
import yaml
import re
import sys
import configparser

# --- InsightFinder Configuration ---
config = configparser.ConfigParser()
config.read('conf.d/config.ini')

base_url = config.get('InsightFinder', 'insightfinder_url')
username = config.get('InsightFinder', 'username')
password = config.get('InsightFinder', 'password')
license_key = config.get('InsightFinder', 'license_key')
# project = config.get('InsightFinder', 'project')
user_agent = "Mozilla/5.0 (compatible; InsightFinderClient/1.0;)"

# --- Database Configuration ---
DB_FILE = "devices.db"
TABLE_NAME = "devices"
OUTPUT_YAML_FILE = "instance_metadata.yaml"

def sanitize_name(name):
    """Removes all special characters from a string, leaving only alphanumeric characters."""
    if not name:
        return ""
    return re.sub(r'[^a-zA-Z0-9]', '', name)

# --- InsightFinder Functions ---
def login(session: requests.Session):
    """Performs login to retrieve token and session ID."""
    login_url = f"{base_url}/api/v1/login-check"
    login_params = {"userName": username, "password": password}
    login_response = session.post(login_url, params=login_params, headers={"User-Agent": user_agent, "Content-Type": "application/json"})
    if login_response.status_code != 200:
        print(f"Login failed: {login_response.text}")
        sys.exit(1)
    login_data = login_response.json()
    if not login_data.get("valid", False):
        print("Invalid login credentials.")
        sys.exit(1)
    return login_data.get("token", "")

def loadProjectsMetaDataInfo(session: requests.Session, token: str, projectName: str):
    """Loads project metadata from InsightFinder."""
    projectList = [{"projectName": projectName, "customerName": username}]
    form_data = {"projectList": json.dumps(projectList), "includeInstance": True}
    metadata_response = session.post(
        f"{base_url}/api/v1/loadProjectsMetaDataInfo",
        data=form_data,
        params={'tzOffset': -18000000},
        headers={"User-Agent": user_agent, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "X-CSRF-TOKEN": token}
    )
    return metadata_response.json()

def list_instances_in_project(session: requests.Session, token: str, projectName: str):
    """Lists all instances in a given InsightFinder project."""
    result = set()
    project_metadata = loadProjectsMetaDataInfo(session, token, projectName)
    if "data" not in project_metadata or not project_metadata["data"]:
        print(f"No data returned for project {projectName}.")
        return []
    if 'instanceStructureSet' not in project_metadata["data"][0]:
        print(f"Error: 'instanceStructureSet' not found for project {projectName}.")
        return []

    instances_dict = project_metadata["data"][0]["instanceStructureSet"]
    for entry in instances_dict:
        if 'i' in entry and entry['i'].strip():
            result.add(entry['i'])
        if 'c' in entry and entry['c']:
            for container in entry['c']:
                result.add(f"{container}_{entry['i']}")
    return list(result)

# --- Database Function ---
def query_device_data(sanitized_device_name: str):
    """Queries the database for a specific sanitized device name and returns the row."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(f"SELECT * FROM {TABLE_NAME} WHERE device_name = ?", (sanitized_device_name,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

# --- Main Processing Function ---
def process_project(project_name_to_query: str, session: requests.Session = None, csrf_token: str = None):
    """
    Process a single project - fetch instances from InsightFinder and map to device data.
    
    Args:
        project_name_to_query: Name of the project to process
        session: Optional requests.Session object (if not provided, will create new one)
        csrf_token: Optional CSRF token (if not provided, will login to get one)
    
    Returns:
        Dictionary of instance metadata
    """
    print(f"Starting process for project: {project_name_to_query}")
    
    # Create session and login if not provided
    should_close_session = False
    if session is None or csrf_token is None:
        print("Logging into InsightFinder...")
        session = requests.Session()
        csrf_token = login(session)
        should_close_session = True
    
    try:
        # 1. Fetch instances from InsightFinder
        print("Fetching instances...")
        instance_list = list_instances_in_project(session, csrf_token, project_name_to_query)
        if not instance_list:
            print("No instances found or error fetching instances.")
            return {}
        print(f"Found {len(instance_list)} instances.")

        # 2. Query database and build metadata mapping
        all_instance_metadata = {}
        print("Querying database for each instance...")
        for original_instance_name in instance_list:
            sanitized_instance = sanitize_name(original_instance_name)
            if not sanitized_instance:
                print(f"Skipping instance '{original_instance_name}' (empty after sanitization).")
                continue

            device_info = query_device_data(sanitized_instance)
            if device_info:
                all_instance_metadata[original_instance_name] = device_info
            else:
                all_instance_metadata[original_instance_name] = {"error": "Device not found in database"}

        # 3. Store the results in a YAML file
        print(f"Writing collected metadata to '{OUTPUT_YAML_FILE}'...")
        with open(OUTPUT_YAML_FILE, 'w') as f:
            yaml.dump(all_instance_metadata, f, indent=2, sort_keys=False)

        print("Process completed successfully.")
        return all_instance_metadata
    finally:
        # Only close session if we created it in this function
        if should_close_session and session:
            session.close()

# --- Main Execution ---
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <project_name>")
        sys.exit(1)

    project_name = sys.argv[1]
    process_project(project_name)
