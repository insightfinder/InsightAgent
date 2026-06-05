#!/usr/bin/env python3
"""
Step 2: For each configured Application Service, pull its dependency map from
ServiceNow and flatten it into source -> target relations.

Uses the CMDB Application Service REST API:
    GET /api/now/cmdb/app_service/{sys_id}/getContent?mode=shallow
which returns every CI in the service map plus the parent/child relationships
between them in a single call.

Output: servicenow_dependencies.yaml -- a list of relation dicts:
    - source: <parent CI name>
      target: <child CI name>
      zone_name: <Application Service name>
      original_source: <parent CI name>
      original_target: <child CI name>
"""

import logging
import requests
import yaml
import config
from servicenow_session import get_servicenow_session

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_yaml_file(filepath):
    """Load YAML file and return data."""
    try:
        with open(filepath, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
        raise


def get_service_content(session, base_url, sys_id, mode):
    """
    Call the Application Service getContent API for one service.
    Returns the 'result' object, or None on failure.
    """
    endpoint = f"{base_url.rstrip('/')}/api/now/cmdb/app_service/{sys_id}/getContent"
    params = {"mode": mode}

    try:
        response = session.get(endpoint, params=params, timeout=120)
        logger.info(f"  getContent for {sys_id} -> status {response.status_code}")
        response.raise_for_status()
        return response.json().get("result", {})
    except requests.exceptions.RequestException as e:
        logger.error(f"  Failed to fetch content for service {sys_id}: {e}")
        if getattr(e, "response", None) is not None:
            logger.error(f"  Response content: {e.response.text}")
        return None


def build_relations(result, zone_name, direction):
    """
    Turn a getContent 'result' object into a list of relation dicts.

    result['cis']: list of CIs, each with sys_id / name / sys_class_name
    result['service_relations']: list of {parent: <sys_id>, child: <sys_id>}
    """
    cis = result.get("cis", []) or []
    service_relations = result.get("service_relations", []) or []

    # Map CI sys_id -> human-readable name.
    name_by_sysid = {}
    for ci in cis:
        sys_id = ci.get("sys_id")
        name = ci.get("name") or sys_id
        if sys_id:
            name_by_sysid[sys_id] = name

    relations = []
    skipped = 0
    for rel in service_relations:
        parent_id = rel.get("parent")
        child_id = rel.get("child")
        if not parent_id or not child_id:
            skipped += 1
            continue

        parent_name = name_by_sysid.get(parent_id, parent_id)
        child_name = name_by_sysid.get(child_id, child_id)

        # Map parent/child onto source/target per configured direction.
        if direction == "child_to_parent":
            source_name, target_name = child_name, parent_name
        else:  # default: parent_to_child
            source_name, target_name = parent_name, child_name

        relations.append({
            "source": source_name,
            "target": target_name,
            "zone_name": zone_name,
            "original_source": source_name,
            "original_target": target_name,
        })

    if skipped:
        logger.warning(f"  Skipped {skipped} relation(s) missing a parent or child sys_id")

    return relations


def main():
    """Main execution function."""
    logger.info("=" * 80)
    logger.info("ServiceNow: Fetching Application Service dependency maps")
    logger.info("=" * 80)

    service_names = load_yaml_file("application_services.yaml")
    if not service_names:
        logger.warning("application_services.yaml is empty. Run get_application_services.py first.")
        return

    direction = getattr(config, "servicenow_relation_direction", "parent_to_child")
    mode = getattr(config, "servicenow_content_mode", "shallow")

    session = get_servicenow_session()

    all_relations = []
    for sys_id, zone_name in service_names.items():
        logger.info(f"\nProcessing service '{zone_name}' ({sys_id})...")
        result = get_service_content(
            session,
            config.servicenow_url,
            sys_id,
            mode,
        )
        if not result:
            logger.error(f"  No content returned for '{zone_name}'. Skipping.")
            continue

        relations = build_relations(result, zone_name, direction)
        logger.info(f"  Built {len(relations)} relation(s) for '{zone_name}'")
        all_relations.extend(relations)

    # De-duplicate identical (source, target, zone) edges.
    seen = set()
    deduped = []
    for rel in all_relations:
        key = (rel["source"], rel["target"], rel["zone_name"])
        if key not in seen:
            seen.add(key)
            deduped.append(rel)
    if len(deduped) != len(all_relations):
        logger.info(f"Removed {len(all_relations) - len(deduped)} duplicate relation(s)")

    with open("servicenow_dependencies.yaml", "w") as f:
        yaml.dump(deduped, f, default_flow_style=False, sort_keys=False)

    logger.info(f"\nSaved {len(deduped)} relation(s) to servicenow_dependencies.yaml")


if __name__ == "__main__":
    main()
