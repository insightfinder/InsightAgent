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
  - svc_ci_assoc  : which CIs belong to the service (service_id -> ci_id)
  - cmdb_rel_ci   : parent/child relationships between CIs (with their type)
  - cmdb_rel_type : the semantics of each relationship (parent/child descriptors)
  - cmdb_ci       : CI sys_id -> display name

Edge direction:
  InsightFinder reads `source -> target` as "an issue on `source` can cause
  issues on `target`" -- so `source` must be the provider/root and `target` the
  dependent. ServiceNow's parent/child columns do NOT encode that directly: the
  meaning depends on the relationship TYPE. For "Depends on::Used by" the parent
  depends on the child (child is the root), while for "Contains::Contained by"
  the parent contains the child (parent is the root). We therefore resolve each
  edge's type and orient it by impact direction, rather than using a fixed
  parent/child mapping.

Output: servicenow_dependencies.yaml -- a list of relation dicts:
    - source: <provider/root CI name>
      target: <dependent CI name>
      zone_name: <service name>
      original_source: <provider/root CI name>
      original_target: <dependent CI name>
"""

import logging
from collections import Counter

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

# --- Relationship orientation -------------------------------------------------
# InsightFinder edge semantics: source -> target means "an issue on source can
# cause issues on target", so source must be the provider/root and target the
# dependent. ServiceNow's parent/child columns do NOT encode that -- the meaning
# depends on the relationship TYPE. We decide which endpoint is the provider
# from the type's PARENT descriptor (the phrase describing what the parent does
# to the child, e.g. "Depends on", "Contains").
#
# These DEFAULT_* sets cover the standard CMDB relationship types. Instance- or
# Service-Mapping-specific types are added via config (servicenow_*_types) and
# merged in by build_type_sets() -- no code change required.
#
# parent descriptor where the PARENT is the dependent (relies on the child)
#   -> the CHILD is the provider/root -> source = child, target = parent.
DEFAULT_PARENT_IS_DEPENDENT = {
    "depends on",
    "runs on",
    "hosted on",
    "virtualized by",
    "registered on",
    "uses",
    "managed by",
    "powered by",
    "cooled by",
    "connects to",
    "contained by",
    "owned by",
    "provided by",
    "member of",
    "receives data from",
}
# parent descriptor where the PARENT is the provider/root (the child relies on
# it) -> source = parent, target = child.
DEFAULT_PARENT_IS_PROVIDER = {
    "contains",
    "owns",
    "provides",
    "hosts",
    "powers",
    "cools",
    "manages",
    "virtualizes",
    "sends data to",
    "used by",
    "has registered on it",
}
# Structural hosting/containment relationships (host <-> the things it runs).
# These are real impact edges but are noisier than service dependencies, so
# they are gated behind the servicenow_include_containment config toggle.
DEFAULT_CONTAINMENT = {
    "contains",
    "contained by",
    "runs on",
    "runs",
    "hosted on",
    "hosts",
    "registered on",
    "has registered on it",
    "owns",
    "owned by",
    "virtualized by",
    "virtualizes",
}


# --- Host rollup (node-level map) ---------------------------------------------
# When servicenow_rollup_to_host is True, every component CI (process, app
# server, endpoint, ...) is attributed to its host node and edges are projected
# to host -> host, mirroring the collapsed server-to-server view in the UI.
#
# A member is a "host node" if its sys_class_name contains one of these tokens.
# Extend/override via config.servicenow_node_host_classes.
DEFAULT_HOST_CLASSES = {
    "server",
    "computer",
    "hardware",
    "esx",
    "vmware",
    "netgear",
    "switch",
    "router",
    "firewall",
    "storage",
    "load_balancer",
}
# Relationship descriptors (beyond containment) that attribute a component to a
# host: the process that implements an endpoint hosts that endpoint.
HOSTING_EXTRA = {"implement end point to", "implement end point from"}

# Software/component classes that contain a host token (e.g. "app_server",
# "web_server" both contain "server") but are NOT hosts. Checked first so these
# never get mistaken for a host node.
COMPONENT_CLASS_TOKENS = {
    "app_server",
    "web_server",
    "appl",
    "application",
    "endpoint",
    "process",
    "web_service",
    "web_site",
    "soap",
    "rest",
    "daemon",
    "software",
    "db_instance",
    "db_catalog",
    "running",
}


def _normalize(items):
    """Lowercase/strip a config list into a set, ignoring blanks/non-strings."""
    return {str(x).strip().lower() for x in (items or []) if str(x).strip()}


def _is_host_class(sys_class_name, host_classes):
    """True if the CI's class marks it as a top-level host/node.

    Software/component classes (app_server, web_server, endpoint, ...) are
    excluded first so they are never mistaken for a host, even though some
    contain a host token like "server".
    """
    cls = (sys_class_name or "").strip().lower()
    if not cls:
        return False
    if any(token in cls for token in COMPONENT_CLASS_TOKENS):
        return False
    return any(token in cls for token in host_classes)


def _is_hosting(type_info, type_sets):
    """True for relationships that attribute a component to its host
    (containment plus 'implement end point')."""
    return is_containment(type_info, type_sets) or _matches(type_info, HOSTING_EXTRA)


def resolve_hosts(member_ids, classes, edges, type_map, type_sets, host_classes):
    """Map each member CI sys_id to its host-node sys_id (or None if unresolved).

    Host-class CIs map to themselves. Other CIs are walked up the hosting graph
    (Runs on / Contains / Hosted on / Implement end point / ...) to the nearest
    host-class ancestor.
    """
    # host_ward[dependent] = the host-side CI for each hosting edge.
    host_ward = {}
    for parent_id, child_id, type_id in edges:
        type_info = type_map.get(type_id, {})
        if not _is_hosting(type_info, type_sets):
            continue
        ori = orientation(type_info, type_sets)
        if ori is None:
            continue
        if ori == "parent_source":
            hostward, dependent = parent_id, child_id
        else:
            hostward, dependent = child_id, parent_id
        host_ward.setdefault(dependent, hostward)

    def resolve(ci):
        seen = set()
        cur = ci
        while cur is not None and cur not in seen:
            if _is_host_class(classes.get(cur, ""), host_classes):
                return cur
            seen.add(cur)
            cur = host_ward.get(cur)
        return None

    return {ci: resolve(ci) for ci in member_ids}


def build_display_names(member_ids, names, classes, edges, type_map, type_sets,
                        host_classes, qualify_common, name_counts, host_of=None):
    """Return {sys_id: display_name} used to identify each CI in the output.

    Default (qualify_common=False): the raw display name, matching the original
    behavior -- distinct CIs that share a name will merge downstream.

    qualify_common=True: any name held by more than one CI (per name_counts,
    tallied across all ingested services) is disambiguated as "<name>@<host>",
    where host is the CI's nearest host-class ancestor. Unique names, and common
    names whose host cannot be resolved, are returned unchanged.
    """
    if not qualify_common:
        return {ci: names.get(ci, ci) for ci in member_ids}

    if host_of is None:
        host_of = resolve_hosts(member_ids, classes, edges, type_map, type_sets,
                                host_classes)

    display = {}
    qualified = unresolved = 0
    for ci in member_ids:
        base = names.get(ci, ci)
        if name_counts.get(base, 0) > 1:
            host_id = host_of.get(ci)
            if host_id and host_id != ci:
                display[ci] = f"{base}@{names.get(host_id, host_id)}"
                qualified += 1
                continue
            unresolved += 1
        display[ci] = base

    if qualified or unresolved:
        logger.info(f"  Common-name qualification: {qualified} CI(s) -> name@host; "
                    f"{unresolved} common-named CI(s) had no resolvable host (left bare)")
    return display


def build_type_sets():
    """Merge the built-in defaults with the config-provided type lists.

    Config lists extend (never replace) the defaults, so standard CMDB types
    keep working while instance-specific types can be added in config.py.
    """
    return {
        "dependent": DEFAULT_PARENT_IS_DEPENDENT | _normalize(
            getattr(config, "servicenow_child_is_source_types", [])),
        "provider": DEFAULT_PARENT_IS_PROVIDER | _normalize(
            getattr(config, "servicenow_parent_is_source_types", [])),
        "containment": DEFAULT_CONTAINMENT | _normalize(
            getattr(config, "servicenow_containment_types", [])),
    }


def _type_descriptors(type_info):
    """Return (parent_descriptor, child_descriptor) lowercased/stripped.

    Falls back to the two segments of the "Parent::Child" type name when the
    explicit descriptor fields are not populated.
    """
    name = type_info.get("name") or ""
    parent_desc = (type_info.get("parent_descriptor") or "").strip().lower()
    child_desc = (type_info.get("child_descriptor") or "").strip().lower()
    if not parent_desc or not child_desc:
        segments = name.split("::", 1)
        if not parent_desc and segments:
            parent_desc = segments[0].strip().lower()
        if not child_desc and len(segments) > 1:
            child_desc = segments[1].strip().lower()
    return parent_desc, child_desc


def _matches(type_info, name_set):
    """True if the type's parent descriptor OR its full name is in name_set.

    Lets config entries be written as either the parent descriptor
    ("Applicative Flow To") or the full type name
    ("Applicative Flow To::Applicative Flow From").
    """
    parent_desc, _ = _type_descriptors(type_info)
    full_name = (type_info.get("name") or "").strip().lower()
    return parent_desc in name_set or (full_name != "" and full_name in name_set)


def orientation(type_info, type_sets):
    """'child_source' | 'parent_source' | None.

    'child_source'  -> the child CI is the provider/root (source = child).
    'parent_source' -> the parent CI is the provider/root (source = parent).
    None            -> type is not recognized; caller should skip and log it.
    """
    if _matches(type_info, type_sets["provider"]):
        return "parent_source"
    if _matches(type_info, type_sets["dependent"]):
        return "child_source"
    return None


def is_containment(type_info, type_sets):
    """True for structural hosting/containment relationship types."""
    return _matches(type_info, type_sets["containment"])


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


def get_ci_details(session, base_url, ci_ids):
    """Return (names, classes) dicts {sys_id: name} and {sys_id: sys_class_name}
    for the given CI sys_ids."""
    endpoint = f"{base_url.rstrip('/')}/api/now/table/cmdb_ci"
    names = {}
    classes = {}
    for chunk in _chunks(ci_ids, CHUNK_SIZE):
        params = {
            "sysparm_query": "sys_idIN" + ",".join(chunk),
            "sysparm_fields": "sys_id,name,sys_class_name",
            "sysparm_limit": 100000,
        }
        resp = session.get(endpoint, params=params, timeout=120)
        resp.raise_for_status()
        for row in resp.json().get("result", []):
            sys_id = row.get("sys_id")
            if sys_id:
                names[sys_id] = row.get("name") or sys_id
                classes[sys_id] = row.get("sys_class_name") or ""
    return names, classes


def get_rel_type_map(session, base_url):
    """Return {type_sys_id: {name, parent_descriptor, child_descriptor}} for all
    relationship types, used to orient each edge by impact direction."""
    endpoint = f"{base_url.rstrip('/')}/api/now/table/cmdb_rel_type"
    params = {
        "sysparm_fields": "sys_id,name,parent_descriptor,child_descriptor",
        "sysparm_limit": 100000,
    }
    resp = session.get(endpoint, params=params, timeout=120)
    resp.raise_for_status()
    type_map = {}
    for row in resp.json().get("result", []):
        sys_id = row.get("sys_id")
        if sys_id:
            type_map[sys_id] = {
                "name": row.get("name") or "",
                "parent_descriptor": row.get("parent_descriptor") or "",
                "child_descriptor": row.get("child_descriptor") or "",
            }
    return type_map


def get_relationships(session, base_url, ci_ids):
    """
    Return intra-service dependency edges as a list of
    (parent_sys_id, child_sys_id, type_sys_id).
    Only edges where BOTH endpoints are members of the service are kept.
    """
    members = set(ci_ids)
    edges = []
    dropped_external = 0
    endpoint = f"{base_url.rstrip('/')}/api/now/table/cmdb_rel_ci"
    for chunk in _chunks(ci_ids, CHUNK_SIZE):
        params = {
            "sysparm_query": "parentIN" + ",".join(chunk),
            "sysparm_fields": "parent,child,type",
            "sysparm_limit": 100000,
        }
        resp = session.get(endpoint, params=params, timeout=120)
        resp.raise_for_status()
        for rel in resp.json().get("result", []):
            parent = _ref_value(rel.get("parent"))
            child = _ref_value(rel.get("child"))
            type_id = _ref_value(rel.get("type"))
            if not parent or not child:
                continue
            if parent in members and child in members:
                edges.append((parent, child, type_id))
            else:
                dropped_external += 1
    if dropped_external:
        logger.info(f"    ({dropped_external} edge(s) pointed outside the service and were dropped)")
    return edges


def build_relations(edges, display_names, type_map, type_sets, zone_name, include_containment,
                    skip_stats, host_of=None):
    """Turn (parent, child, type) sys_id edges into named source/target relations.

    Direction is decided per relationship type so that source -> target always
    means "an issue on source can impact target". Edges with an unrecognized
    type are skipped (recorded in skip_stats['unknown']); containment edges are
    skipped when include_containment is False (recorded in skip_stats['containment']).

    When host_of is provided (rollup mode), each endpoint is mapped to its host
    node before naming: intra-host edges collapse and are dropped, and edges with
    an endpoint that can't be attributed to a host are skipped
    (recorded in skip_stats['unresolved']).
    """
    relations = []
    for parent_id, child_id, type_id in edges:
        type_info = type_map.get(type_id, {})
        type_name = type_info.get("name") or type_id or "(missing type)"

        ori = orientation(type_info, type_sets)
        if ori is None:
            skip_stats["unknown"][type_name] += 1
            continue

        if is_containment(type_info, type_sets) and not include_containment:
            skip_stats["containment"][type_name] += 1
            continue

        # Orient so source = provider/root, target = dependent.
        if ori == "child_source":
            source_id, target_id = child_id, parent_id
        else:  # parent_source
            source_id, target_id = parent_id, child_id

        if host_of is not None:
            source_id = host_of.get(source_id)
            target_id = host_of.get(target_id)
            if not source_id or not target_id:
                skip_stats["unresolved"][type_name] += 1
                continue
            if source_id == target_id:
                continue  # intra-host edge collapses away

        source_name = display_names.get(source_id, source_id)
        target_name = display_names.get(target_id, target_id)

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

    include_containment = getattr(config, "servicenow_include_containment", True)
    rollup = getattr(config, "servicenow_rollup_to_host", False)
    qualify_common = getattr(config, "servicenow_qualify_common_names", False)
    host_classes = _normalize(getattr(config, "servicenow_node_host_classes", None)) or DEFAULT_HOST_CLASSES
    if rollup:
        logger.info("Granularity: NODE-level (rolling components up to host nodes)")
    else:
        logger.info("Granularity: component-level (full CI graph)")
        logger.info(f"Containment relationships (Runs on/Contains/...): "
                    f"{'included' if include_containment else 'excluded'}")
    logger.info(f"Common-name qualification (name@host): "
                f"{'on' if qualify_common else 'off'}")

    session = get_servicenow_session()

    type_map = get_rel_type_map(session, config.servicenow_url)
    logger.info(f"Loaded {len(type_map)} relationship type(s) from cmdb_rel_type")

    type_sets = build_type_sets()

    # Skip tallies, shared across services, reported once at the end.
    skip_stats = {"unknown": Counter(), "containment": Counter(), "unresolved": Counter()}

    # Phase 1: pull each service's CIs/edges, and tally how many distinct CIs
    # share each display name (across all services) so build_display_names can
    # tell which names are "common" and need host qualification.
    fetched = []
    name_sysids = {}  # display name -> set of sys_ids that use it
    for sys_id, zone_name in service_names.items():
        zone_name = zone_name or "NO_ZONE"
        logger.info(f"\nProcessing service '{zone_name}' ({sys_id})...")

        member_ids = get_member_ci_ids(session, config.servicenow_url, sys_id)
        logger.info(f"  {len(member_ids)} member CI(s)")
        if not member_ids:
            logger.warning(f"  No member CIs found for '{zone_name}'. Skipping.")
            continue

        names, classes = get_ci_details(session, config.servicenow_url, member_ids)
        edges = get_relationships(session, config.servicenow_url, member_ids)

        fetched.append((zone_name, member_ids, names, classes, edges))
        for ci in set(member_ids):
            name_sysids.setdefault(names.get(ci, ci), set()).add(ci)

    name_counts = {name: len(ids) for name, ids in name_sysids.items()}

    # Phase 2: orient and name each service's edges.
    all_relations = []
    for zone_name, member_ids, names, classes, edges in fetched:
        host_of = None
        if rollup:
            host_of = resolve_hosts(member_ids, classes, edges, type_map, type_sets, host_classes)
            n_hosts = len(set(filter(None, host_of.values())))
            n_unmapped = sum(1 for h in host_of.values() if not h)
            logger.info(f"  Resolved {n_hosts} host node(s); "
                        f"{n_unmapped} member(s) could not be attributed to a host")

        display_names = build_display_names(
            member_ids, names, classes, edges, type_map, type_sets, host_classes,
            qualify_common, name_counts, host_of=host_of
        )

        relations = build_relations(
            edges, display_names, type_map, type_sets, zone_name, include_containment,
            skip_stats, host_of=host_of
        )
        logger.info(f"  Built {len(relations)} relation(s) for '{zone_name}'")
        all_relations.extend(relations)

    # Report skipped edges so the type mapping can be reviewed/extended.
    if skip_stats["unknown"]:
        total = sum(skip_stats["unknown"].values())
        logger.warning(f"\nSkipped {total} edge(s) with unrecognized relationship type(s):")
        for type_name, count in skip_stats["unknown"].most_common():
            logger.warning(f"    {count:>6}  {type_name}")
        logger.warning("    -> add these to servicenow_child_is_source_types or "
                       "servicenow_parent_is_source_types in config.py to include them.")
    if skip_stats["containment"]:
        total = sum(skip_stats["containment"].values())
        logger.info(f"\nExcluded {total} containment edge(s) "
                    f"(servicenow_include_containment=False):")
        for type_name, count in skip_stats["containment"].most_common():
            logger.info(f"    {count:>6}  {type_name}")
    if skip_stats["unresolved"]:
        total = sum(skip_stats["unresolved"].values())
        logger.info(f"\nDropped {total} edge(s) whose endpoint(s) could not be "
                    f"attributed to a host node (rollup mode):")
        for type_name, count in skip_stats["unresolved"].most_common():
            logger.info(f"    {count:>6}  {type_name}")

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
