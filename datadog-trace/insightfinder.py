#!/usr/bin/env python3
"""
InsightFinder integration utilities.

Provides helpers for sending data to the InsightFinder API.
"""

import json
import urllib.request
import urllib.error
from typing import Any

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
        urllib.error.HTTPError: On non-2xx HTTP responses.
        urllib.error.URLError:  On network-level errors.
    """
    url = f"{if_url.rstrip('/')}/api/v1/customprojectrawdata"

    payload = json.dumps(
        {
            "userName": user_name,
            "projectName": project_name,
            "licenseKey": license_key,
            "agentType": agent_type,
            "metricData": metric_data,
            "systemName": system_name,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "agent-type": "Stream",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())