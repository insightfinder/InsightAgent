import configparser
import yaml
import json
import re
import requests
import sys

CONFIG_FILE = "conf.d/config.ini"
METADATA_FILE = "instance_metadata.yaml"

def generate_payload():
    """
    Generates a JSON payload based on instance metadata and JIRA field mappings,
    and sends it to the InsightFinder API.
    """
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    with open(METADATA_FILE, 'r') as f:
        metadata = yaml.safe_load(f)

    field_mapping = config['Jira_Field_Mapping']
    workspace_id = config['Jira']['workspace_id']

    # InsightFinder config
    if_config = config['InsightFinder']
    if_url = if_config['insightfinder_url']
    username = if_config['username']
    license_key = if_config['license_key']

    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <project_name>")
        sys.exit(1)
    project = sys.argv[1]

    payload = []
    for instance_name, instance_data in metadata.items():
        if "error" in instance_data:
            continue

        jira_issue_fields = {}
        for custom_field, yaml_key in field_mapping.items():
            if yaml_key in instance_data:
                yaml_value = str(instance_data[yaml_key])
                sanitized_value = re.sub(r'\D', '', yaml_value)
                jira_issue_fields[custom_field] = f"{workspace_id}:{sanitized_value}"

        instance_payload = {
            "instanceName": instance_name,
            "jiraConfigs": {
                "jiraIssueFields": jira_issue_fields
            }
        }
        payload.append(instance_payload)

    # Prepare for InsightFinder API call
    endpoint = f"{if_url}/api/v1/agent-upload-third-party-instancemetadata"
    params = {
        "customerName": username,
        "licenseKey": license_key,
        "projectName": project
    }

    try:
        response = requests.post(endpoint, json=payload, params=params)
        response.raise_for_status()  # Raise an exception for bad status codes
        print("Payload successfully sent to InsightFinder.")
        print(f"Response: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending payload to InsightFinder: {e}")

if __name__ == "__main__":
    generate_payload()