#!/usr/bin/env python3
"""
InsightFinder metric integration helper.

Sends numeric metric data to an InsightFinder metric project via the
/api/v2/metric-data-receive endpoint.
"""

import logging
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

_COMMON_FIELDS = {"instanceName", "componentName", "timestamp", "device_type", "host_id"}


def check_and_create_project(
    *,
    user_name: str,
    license_key: str,
    project_name: str,
    system_name: str,
    sampling_interval: int,
    if_url: str,
) -> bool:
    url = f"{if_url.rstrip('/')}/api/v1/check-and-add-custom-project"
    base_params = {
        "userName": user_name,
        "licenseKey": license_key,
        "projectName": project_name,
    }

    try:
        resp = requests.post(url, data={**base_params, "operation": "check"}, timeout=15, verify=False)
        resp.raise_for_status()
        result = resp.json()
        if result.get("success") and result.get("isProjectExist"):
            log.info("Project already exists: %s", project_name)
            return True
    except Exception as exc:
        log.error("Project check failed: %s", exc)
        return False

    log.info("Project not found — creating: %s", project_name)
    try:
        resp = requests.post(
            url,
            data={
                **base_params,
                "operation": "create",
                "systemName": system_name or project_name,
                "instanceType": "Datadog",
                "projectCloudType": "Datadog",
                "dataType": "Metric",
                "insightAgentType": "Custom",
                "samplingInterval": sampling_interval,
                "samplingIntervalInSeconds": sampling_interval,
            },
            timeout=15,
            verify=False,
        )
        resp.raise_for_status()
        result = resp.json()
        if not result.get("success"):
            log.error("Project creation failed: %s", result)
            return False
        log.info("Project created: %s", project_name)
    except Exception as exc:
        log.error("Project creation error: %s", exc)
        return False

    time.sleep(10)
    try:
        resp = requests.post(url, data={**base_params, "operation": "check"}, timeout=15, verify=False)
        resp.raise_for_status()
        result = resp.json()
        if result.get("success") and result.get("isProjectExist"):
            log.info("Project confirmed ready: %s", project_name)
            return True
        log.error("Project not ready after creation: %s", result)
        return False
    except Exception as exc:
        log.error("Project re-check failed: %s", exc)
        return False


def send_metric_data_to_if(
    *,
    user_name: str,
    license_key: str,
    project_name: str,
    system_name: str,
    metric_rows: list[dict[str, Any]],
    if_url: str,
) -> dict:
    instance_data_map: dict[str, Any] = {}

    for row in metric_rows:
        instance = str(row.get("instanceName") or "unknown")
        component = row.get("componentName")
        device_type = row.get("device_type")
        host_id = row.get("host_id")
        ts_ms = int(row["timestamp"])

        if instance not in instance_data_map:
            instance_data_map[instance] = {
                "in": instance,
                "cn": component,
                "ct": device_type,
                "dit": {},
            }

        dit = instance_data_map[instance]["dit"]
        if ts_ms not in dit:
            dit[ts_ms] = {"t": ts_ms, "m": []}

        if host_id:
            dit[ts_ms]["k"] = {"hostId": host_id}

        metrics = dit[ts_ms]["m"]
        for key, val in row.items():
            if key in _COMMON_FIELDS:
                continue
            try:
                metrics.append({"m": key, "v": float(val)})
            except (TypeError, ValueError):
                pass

    payload = {
        "licenseKey": license_key,
        "userName": user_name,
        "data": {
            "projectName": project_name,
            "userName": user_name,
            "systemName": system_name,
            "idm": instance_data_map,
        },
    }

    url = f"{if_url.rstrip('/')}/api/v2/metric-data-receive"
    resp = requests.post(
        url,
        json=payload,
        headers={"Accept": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()
