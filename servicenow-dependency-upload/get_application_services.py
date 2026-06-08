#!/usr/bin/env python3
"""
Step 1: Look up the display name of each configured ServiceNow Application
Service (by sys_id) and save a sys_id -> name mapping to
application_services.yaml.

These names become the InsightFinder "zone" for each service map, the same way
venues.yaml supplies zone names in the Zabbix/Jira pipeline.
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


def fetch_service_names(session, base_url, table, sys_ids):
    """
    Fetch the 'name' field for each service sys_id from the given table.
    Returns a dict {sys_id: name}.
    """
    if not sys_ids:
        logger.warning("No service sys_ids configured (servicenow_service_sys_ids is empty).")
        return {}

    endpoint = f"{base_url.rstrip('/')}/api/now/table/{table}"
    # sysparm_query: sys_idIN<id1>,<id2>,...  -> fetch all requested rows at once
    query = "sys_idIN" + ",".join(sys_ids)
    params = {
        "sysparm_query": query,
        "sysparm_fields": "sys_id,name",
        "sysparm_limit": len(sys_ids),
    }

    logger.info(f"Looking up {len(sys_ids)} service name(s) from table '{table}'...")
    response = session.get(endpoint, params=params, timeout=60)
    logger.info(f"Request completed with status code: {response.status_code}")
    response.raise_for_status()

    rows = response.json().get("result", [])
    service_names = {}
    for row in rows:
        sys_id = row.get("sys_id")
        name = row.get("name")
        if sys_id and name:
            service_names[sys_id] = name

    # Warn about any configured sys_ids we couldn't resolve a name for.
    missing = [sid for sid in sys_ids if sid not in service_names]
    if missing:
        logger.warning(
            f"Could not find a name for {len(missing)} sys_id(s) in '{table}': {missing}. "
            f"They will still be processed using the sys_id as the zone name."
        )
        for sid in missing:
            service_names[sid] = sid  # fall back to sys_id as the zone name

    return service_names


def main():
    """Main function to resolve service names and save to file."""
    logger.info("=" * 80)
    logger.info("ServiceNow: Resolving Application Service names")
    logger.info("=" * 80)

    fetch_zone_name = getattr(config, "servicenow_fetch_zone_name", False) or False

    if not fetch_zone_name:
        # Skip the ServiceNow lookup entirely; assign every configured service
        # the default zone. application_services.yaml is still written so that
        # steps 2 and 3 work unchanged.
        default_zone = getattr(config, "servicenow_default_zone", "NO_ZONE")
        logger.info(
            f"servicenow_fetch_zone_name is False -- skipping name lookup; "
            f"using default zone '{default_zone}' for all services."
        )
        service_names = {sid: default_zone for sid in config.servicenow_service_sys_ids}
    else:
        session = get_servicenow_session()
        service_names = fetch_service_names(
            session,
            config.servicenow_url,
            getattr(config, "servicenow_app_service_table", None) or "cmdb_ci_service",
            config.servicenow_service_sys_ids,
        )

    if not service_names:
        logger.warning("No services to process. Nothing written.")
        return

    with open("application_services.yaml", "w") as f:
        yaml.dump(service_names, f, indent=2, sort_keys=False)

    logger.info(f"Saved {len(service_names)} service(s) to application_services.yaml")
    logger.info("\n--- Service Summary ---")
    for sys_id, name in service_names.items():
        logger.info(f"{sys_id}: {name}")


if __name__ == "__main__":
    main()
