#!/usr/bin/env python3
"""
Step 2: For each configured service, build its dependency map from ServiceNow
and flatten it into source -> target relations.

NOTE: The CMDB Application Service API
    GET /api/now/cmdb/app_service/{sys_id}/getContent
only works on empty or *manual* services. Service Mapping *discovered* services
(the kind behind a $sw_topology_map.do URL) return HTTP 400:
    "This API is allowed to operate only on empty or manual service.
     This service contains discovered elements"
So we build the map from the underlying CMDB tables instead:
  - svc_ci_assoc : which CIs belong to the service (service_id -> ci_id)
  - cmdb_rel_ci  : parent/child relationships between CIs
  - cmdb_ci      : CI sys_id -> display name

Output: servicenow_dependencies.yaml -- a list of relation dicts:
    - source: <parent CI name>
      target: <child CI name>
      zone_name: <service name>
      original_source: <parent CI name>
      original_target: <child CI name>
"""

import logging
import yaml
import config
from servicenow_session import get_servicenow_session

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# sys_ids per query, kept small to stay under ServiceNow's URL length limit (414).
CHUNK_SIZE = 40


def load_yaml_file(filepath):
    """Load YAML file and return data."""
    try:
        with open(filepath, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
        raise


def _chunks(items, n):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def _ref_value(field):
    """Reference fields come back as {'value': ..., 'link': ...}; plain fields as str."""
    if isinstance(field, dict):
        return field.get('value')
    return field


def get_member_ci_ids(session, base_url, service_sys_id):
    """Return the sys_ids of all CIs associated with a service via svc_ci_assoc."""
    endpoint = f"{base_url.rstrip('/')}/api/now/table/svc_ci_assoc"
    params = {
        "sysparm_query": f"service_id={service_sys_id}",
        "sysparm_fields": "ci_id",
        "sysparm_limit": 100000,
    }
    resp = session.get(endpoint, params=params, timeout=120)
    resp.raise_for_status()
    ids = []
    for row in resp.json().get("result", []):
        val = _ref_value(row.get("ci_id"))
        if val:
            ids.append(val)
    return ids


def get_ci_names(session, base_url, ci_ids):
    """Return a dict {sys_id: name} for the given CI sys_ids."""
    endpoint = f"{base_url.rstrip('/')}/api/now/table/cmdb_ci"
    names = {}
    for chunk in _chunks(ci_ids, CHUNK_SIZE):
        params = {
            "sysparm_query": "sys_idIN" + ",".join(chunk),
            "sysparm_fields": "sys_id,name",
            "sysparm_limit": 100000,
        }
        resp = session.get(endpoint, params=params, timeout=120)
        resp.raise_for_status()
        for row in resp.json().get("result", []):
            sys_id = row.get("sys_id")
            if sys_id:
                names[sys_id] = row.get("name") or sys_id
    return names


def get_relationships(session, base_url, ci_ids):
    """
    Return intra-service dependency edges as a list of (parent_sys_id, child_sys_id).
    Only edges where BOTH endpoints are members of the service are kept.
    """
    members = set(ci_ids)
    edges = []
    dropped_external = 0
    endpoint = f"{base_url.rstrip('/')}/api/now/table/cmdb_rel_ci"
    for chunk in _chunks(ci_ids, CHUNK_SIZE):
        params = {
            "sysparm_query": "parentIN" + ",".join(chunk),
            "sysparm_fields": "parent,child",
            "sysparm_limit": 100000,
        }
        resp = session.get(endpoint, params=params, timeout=120)
        resp.raise_for_status()
        for rel in resp.json().get("result", []):
            parent = _ref_value(rel.get("parent"))
            child = _ref_value(rel.get("child"))
            if not parent or not child:
                continue
            if parent in members and child in members:
                edges.append((parent, child))
            else:
                dropped_external += 1
    if dropped_external:
        logger.info(f"    ({dropped_external} edge(s) pointed outside the service and were dropped)")
    return edges


def build_relations(edges, names, zone_name, direction):
    """Turn (parent, child) sys_id edges into named source/target relation dicts."""
    relations = []
    for parent_id, child_id in edges:
        parent_name = names.get(parent_id, parent_id)
        child_name = names.get(child_id, child_id)

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
    return relations


def main():
    """Main execution function."""
    logger.info("=" * 80)
    logger.info("ServiceNow: Fetching service dependency maps (table-based)")
    logger.info("=" * 80)

    service_names = load_yaml_file("application_services.yaml")
    if not service_names:
        logger.warning("application_services.yaml is empty. Run get_application_services.py first.")
        return

    direction = getattr(config, "servicenow_relation_direction", None) or "parent_to_child"
    session = get_servicenow_session()

    all_relations = []
    for sys_id, zone_name in service_names.items():
        zone_name = zone_name or "NO_ZONE"
        logger.info(f"\nProcessing service '{zone_name}' ({sys_id})...")

        member_ids = get_member_ci_ids(session, config.servicenow_url, sys_id)
        logger.info(f"  {len(member_ids)} member CI(s)")
        if not member_ids:
            logger.warning(f"  No member CIs found for '{zone_name}'. Skipping.")
            continue

        names = get_ci_names(session, config.servicenow_url, member_ids)
        edges = get_relationships(session, config.servicenow_url, member_ids)
        relations = build_relations(edges, names, zone_name, direction)
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
