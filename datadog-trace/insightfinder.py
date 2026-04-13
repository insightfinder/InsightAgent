#!/usr/bin/env python3
"""
InsightFinder integration utilities.

Provides helpers for sending data to the InsightFinder API.
"""

from typing import Any

import requests

IF_ENDPOINT = "https://stg.insightfinder.com"


def send_log_data_to_if(
    user_name: str,
    project_name: str,
    license_key: str,
    metric_data: list[dict[str, Any]],
    system_name: str,
    agent_type: str = "LogStreaming",
    if_url: str = IF_ENDPOINT,
) -> dict:
    """Send log streaming data to InsightFinder.

    Args:
        user_name:    InsightFinder username.
        project_name: Target project name.
        license_key:  InsightFinder license key.
        metric_data:  List of log entries. Each entry must contain:
                        - timestamp (int): epoch milliseconds
                        - tag (str): instance identifier
                        - componentName (str): component identifier
                        - data (dict): log payload
        system_name:  InsightFinder system name.
        agent_type:   Agent type string (default: "LogStreaming").
        if_url:       Base URL of the InsightFinder instance.

    Returns:
        Parsed JSON response from InsightFinder.

    Raises:
        requests.HTTPError: On non-2xx HTTP responses.
        requests.ConnectionError: On network-level errors.
    """
    url = f"{if_url.rstrip('/')}/api/v1/customprojectrawdata"

    resp = requests.post(
        url,
        json={
            "userName": user_name,
            "projectName": project_name,
            "licenseKey": license_key,
            "agentType": agent_type,
            "metricData": metric_data,
            "systemName": system_name,
        },
        headers={
            "agent-type": "Stream",
            "Accept": "application/json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()