#!/usr/bin/env python3
"""
Test script: Send only 5 relations to InsightFinder API.
Shows full request and response for easy debugging.
"""

import re
import json
import logging
import requests
import yaml
import config

INSIGHTFINDER_API_URL = config.insightfinder_url + '/api/v2/updaterelationdependency'

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_validated_instance(instance):
    """Mirrors the IF backend's getValidatedInstance logic."""
    if not instance:
        return 'unknown'
    instance = instance.replace('[', '(')
    instance = instance.replace(']', ')')
    instance = re.sub(r'[,:@]', '.', instance)
    return instance


def sanitize_name(instance):
    """Select sanitization method based on config."""
    if getattr(config, 'use_backend_sanitization', True) is not False:
        return get_validated_instance(instance)
    return instance


def main():
    print("\n" + "=" * 80)
    print("TEST: Send 5 relations to InsightFinder")
    print("=" * 80 + "\n")

    # Load relations
    try:
        with open('servicenow_dependencies.yaml', 'r') as f:
            raw_relations = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load YAML: {e}")
        return

    if not raw_relations:
        logger.error("No relations found")
        return

    # Take only first 5
    test_relations = raw_relations[:5]
    print(f"Loaded {len(raw_relations)} total relations, using first 5 for test\n")

    # Sanitize
    sanitized = []
    for rel in test_relations:
        sanitized.append({
            'source': sanitize_name(rel['source']),
            'target': sanitize_name(rel['target']),
            'zone_name': rel.get('zone_name') or 'NO_ZONE',
        })

    # Print relations
    print("Relations to send:")
    for i, rel in enumerate(sanitized, 1):
        print(f"  {i}. {rel['source']} → {rel['target']} (zone: {rel['zone_name']})")

    # Determine method
    use_put = getattr(config, 'causal_key', '') and config.causal_key.strip()
    http_method = "PUT" if use_put else "POST"

    print(f"\nMethod: {http_method}")
    if use_put:
        print(f"Causal Key: {config.causal_key.strip()}")
    print(f"System: {config.insightfinder_system}")
    print(f"URL: {INSIGHTFINDER_API_URL}\n")

    # Build payload
    instance_relation_list = []
    for rel in sanitized:
        instance_relation_list.append({
            "sources": [{"id": rel['source'], "type": config.relation_node_type}],
            "targets": [{"id": rel['target'], "type": config.relation_node_type}],
            "st": 1
        })

    instance_relation_list_str = json.dumps(instance_relation_list)

    payload = {
        "licenseKey": config.license_key,
        "userName": config.insightfinder_username,
        "projectLevelAddRelationSetStr": instance_relation_list_str,
        "zoneName": "NO_ZONE"
    }

    if use_put:
        payload["causalKey"] = config.causal_key.strip()
    else:
        payload["systemDisplayName"] = config.insightfinder_system

    # Print request
    print("=" * 80)
    print("REQUEST")
    print("=" * 80)
    print(f"Method: {http_method}")
    print(f"URL: {INSIGHTFINDER_API_URL}")
    print(f"Headers: Content-Type: application/json")
    print(f"\nPayload:")
    print(json.dumps(payload, indent=2))

    # Send request
    print("\n" + "=" * 80)
    print("SENDING...")
    print("=" * 80 + "\n")

    try:
        if use_put:
            response = requests.put(
                INSIGHTFINDER_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                verify=False
            )
        else:
            response = requests.post(
                INSIGHTFINDER_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                verify=False
            )

        # Print response
        print("=" * 80)
        print("RESPONSE")
        print("=" * 80)
        print(f"Status Code: {response.status_code}")
        print(f"\nResponse Body:")

        # Try to parse as JSON, otherwise print raw text
        try:
            if response.text:
                print(json.dumps(response.json(), indent=2))
            else:
                print("(empty)")
        except:
            print(f"(raw text): {response.text}")

        if response.status_code == 200:
            print("\n✓ SUCCESS")
        else:
            print(f"\n✗ FAILED ({response.status_code})")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
