#!/usr/bin/env python3
"""
Step 3: Send the ServiceNow dependency relations to the InsightFinder API.
Reads servicenow_dependencies.yaml, sanitizes instance names, groups relations
by zone, and POSTs one request per zone to /api/v2/updaterelationdependency.
"""

import re
import json
import logging
import requests
import sys
import yaml
import config

# Configuration
INSIGHTFINDER_API_URL = config.insightfinder_url + '/api/v2/updaterelationdependency'
TEST_LIMIT = 0  # Limit number of relations to send for testing (0 = send all)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_validated_instance(instance):
    """Mirrors the IF backend's getValidatedInstance logic:
       [ -> (,  ] -> ),  [,:@] -> .
    This ensures uploaded names match exactly what IF stores after its own ingest.
    """
    if not instance:
        return 'unknown'
    instance = instance.replace('[', '(')
    instance = instance.replace(']', ')')
    instance = re.sub(r'[,:@]', '.', instance)
    return instance


def make_safe_instance_string(instance, device=''):
    """Agent-side sanitization (matches elasticsearch_collector convention):
       _ -> .,  : -> -,  strip leading special chars.
    """
    if not instance:
        return 'unknown'
    instance = re.sub(r'\_+', '.', instance)
    instance = re.sub(r'\:+', '-', instance)
    instance = re.sub(r'^[-_\W]+', '', instance)
    if device:
        instance = '{}_{}'.format(make_safe_instance_string(device), instance)
    return instance


def sanitize_name(instance):
    """Select sanitization method based on config."""
    if getattr(config, 'use_backend_sanitization', True) is not False:
        return get_validated_instance(instance)
    return make_safe_instance_string(instance)


def load_yaml_file(filepath):
    """Load YAML file and return data."""
    try:
        with open(filepath, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
        raise


def sanitize_relations(relations):
    """Sanitize source/target names for InsightFinder."""
    method = 'backend' if getattr(config, 'use_backend_sanitization', True) is not False else 'agent'
    logger.info(f"Using {method} sanitization (use_backend_sanitization={method == 'backend'})")
    sanitized = []
    for rel in relations:
        sanitized.append({
            'source': sanitize_name(rel['source']),
            'target': sanitize_name(rel['target']),
            'zone_name': rel.get('zone_name') or 'NO_ZONE',
            'original_source': rel.get('original_source', rel['source']),
            'original_target': rel.get('original_target', rel['target']),
        })
    return sanitized


def send_relations_to_insightfinder(relations):
    """
    Send device relations to InsightFinder API.
    Groups relations by zone and sends one request per zone.
    """
    relations_by_zone = {}
    for relation in relations:
        zone_name = relation['zone_name']
        relations_by_zone.setdefault(zone_name, []).append(relation)

    logger.info(f"Relations grouped into {len(relations_by_zone)} zone(s)")

    # An empty causal_key -> POST (create a new causal group from scratch).
    # A non-empty causal_key -> PUT (update the existing causal group identified
    # by this key). The backend 404s if no group matches the key.
    causal_key = (getattr(config, 'causal_key', '') or '').strip()
    if causal_key:
        logger.info(f"causal_key set -> PUT (update existing causal group '{causal_key}')")
    else:
        logger.info("causal_key empty -> POST (create new causal group)")

    total_sent = 0
    total_failed = 0

    for zone_name, zone_relations in relations_by_zone.items():
        logger.info(f"\nProcessing zone: '{zone_name}' ({len(zone_relations)} relations)")

        instance_relation_list = []
        for rel in zone_relations:
            instance_relation_list.append({
                "sources": [{"id": rel['source'], "type": config.relation_node_type}],
                "targets": [{"id": rel['target'], "type": config.relation_node_type}],
                "st": 1
            })

        instance_relation_list_str = json.dumps(instance_relation_list)

        payload = {
            "systemDisplayName": config.insightfinder_system,
            "licenseKey": config.license_key,
            "userName": config.insightfinder_username,
            "projectLevelAddRelationSetStr": instance_relation_list_str,
            "zoneName": zone_name
        }
        if causal_key:
            payload["causalKey"] = causal_key

        try:
            request_fn = requests.put if causal_key else requests.post
            response = request_fn(
                INSIGHTFINDER_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                verify=False
            )

            if response.status_code == 200:
                logger.info(f"  ✓ Successfully sent {len(zone_relations)} relations for zone '{zone_name}'")
                total_sent += len(zone_relations)
            else:
                logger.error(f"  ✗ Failed to send relations for zone '{zone_name}': {response.status_code}")
                logger.error(f"    Response: {response.text}")
                total_failed += len(zone_relations)
        except Exception as e:
            logger.error(f"  ✗ Error sending relations for zone '{zone_name}': {e}")
            total_failed += len(zone_relations)

    return total_sent, total_failed


def main():
    """Main execution function."""
    logger.info("=" * 80)
    logger.info("Sending ServiceNow Dependency Relations to InsightFinder")
    causal_key = (getattr(config, 'causal_key', '') or '').strip()
    logger.info(f"Mode: {'UPDATE existing causal group (PUT)' if causal_key else 'CREATE new causal group (POST)'}")
    if TEST_LIMIT > 0:
        logger.info(f"TEST MODE: Limiting to first {TEST_LIMIT} relations")
    logger.info("=" * 80)

    try:
        logger.info("\n[1/3] Loading servicenow_dependencies.yaml...")
        raw_relations = load_yaml_file('servicenow_dependencies.yaml')
        if not raw_relations:
            logger.warning("No relations found in servicenow_dependencies.yaml. Nothing to send.")
            return
        logger.info(f"  Loaded {len(raw_relations)} relation(s)")

        logger.info("\n[2/3] Sanitizing relation names...")
        relations = sanitize_relations(raw_relations)

        if TEST_LIMIT > 0 and len(relations) > TEST_LIMIT:
            logger.info(f"[TEST MODE] Limiting from {len(relations)} to {TEST_LIMIT} relations")
            relations = relations[:TEST_LIMIT]

        logger.info("\nSample relations (first 3):")
        for i, rel in enumerate(relations[:3], 1):
            logger.info(f"  {i}. {rel['original_source']} -> {rel['original_target']}")
            logger.info(f"     Sanitized: {rel['source']} -> {rel['target']}")
            logger.info(f"     Zone: {rel['zone_name']}")

        logger.info(f"\n[3/3] Sending {len(relations)} relation(s) to InsightFinder...")
        total_sent, total_failed = send_relations_to_insightfinder(relations)

        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total relations processed: {len(relations)}")
        logger.info(f"Successfully sent: {total_sent}")
        logger.info(f"Failed: {total_failed}")
        logger.info("=" * 80)

        if total_sent > 0:
            logger.info("\n✓ Process completed successfully!")
        else:
            logger.error("\n✗ No relations were sent successfully!")
            sys.exit(1)

    except Exception as e:
        logger.error(f"\n✗ Error: {e}")
        raise


if __name__ == "__main__":
    main()
