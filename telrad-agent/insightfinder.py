from __future__ import annotations

import dataclasses
import json
import logging
import urllib.parse
from typing import Any

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# API endpoint constants
API_METRIC_DATA_RECEIVE = "api/v2/metric-data-receive"
API_CHECK_ADD_PROJECT = "api/v1/check-and-add-custom-project"
API_CUSTOM_PROJECT_RAW_DATA = "api/v1/customprojectrawdata"
LOG_CHUNK_SIZE = 5000

logger = logging.getLogger(__name__)


def _build_session() -> requests.Session:
    """Create a requests session with retry logic for transient errors."""
    s = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1.0,
        backoff_jitter=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("POST",),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


@dataclasses.dataclass
class Config:
    url: str
    user_name: str
    license_key: str
    project_name: str
    agent_type: str
    instance_type: str = "PrivateCloud"
    chunk_size: int = 100000
    create_project: bool = False
    system_name: str | None = None
    data_type: str | None = None
    insight_agent_type: str | None = None
    sampling_interval: int = 600


class InsightFinder:
    """Client for interacting with InsightFinder API."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = _build_session()

        if self.config.create_project and not self.project_existed():
            self.create_custom_project()

    def __enter__(self) -> "InsightFinder":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def close(self) -> None:
        if self.session:
            self.session.close()

    def _build_base_payload(self) -> dict[str, str]:
        return {
            "userName": self.config.user_name,
            "licenseKey": self.config.license_key,
            "projectName": self.config.project_name,
        }

    def send_metric(self, data: dict[str, Any]) -> None:
        """Send metric data to InsightFinder v2 API.

        Args:
            data: idm (instance data map) structure
        """
        if not data:
            logger.warning("No data to send")
            return

        url = urllib.parse.urljoin(self.config.url, API_METRIC_DATA_RECEIVE)
        payload = {
            "userName": self.config.user_name,
            "licenseKey": self.config.license_key,
            "data": {
                "projectName": self.config.project_name,
                "userName": self.config.user_name,
                "iat": self.config.insight_agent_type or "Custom",
                "ct": self.config.instance_type,
                "idm": data,
            },
        }

        num_instances = len(data)
        logger.info(f"Sending data for {num_instances} instance(s)")
        try:
            self._request(url, payload)
            logger.info(f"Successfully sent data for {num_instances} instance(s)")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send data: {e}")
            raise

    def send_log(self, logs: list[dict[str, Any]]) -> None:
        """Send log records to InsightFinder v1 customprojectrawdata endpoint.

        Each record: {"timestamp": int_ms, "tag": str, "data": str, "componentName"?: str}
        Sends in chunks of 5000 records per the API guidance.

        Args:
            logs: List of log records
        """
        if not logs:
            logger.warning("No log data to send")
            return

        url = urllib.parse.urljoin(self.config.url, API_CUSTOM_PROJECT_RAW_DATA)
        total_chunks = (len(logs) + LOG_CHUNK_SIZE - 1) // LOG_CHUNK_SIZE
        for chunk_num, i in enumerate(range(0, len(logs), LOG_CHUNK_SIZE), start=1):
            chunk = logs[i : i + LOG_CHUNK_SIZE]
            payload = {
                "userName": self.config.user_name,
                "licenseKey": self.config.license_key,
                "projectName": self.config.project_name,
                "agentType": self.config.agent_type,
                "metricData": json.dumps(chunk),
            }
            logger.debug(f"Sending log chunk {chunk_num}/{total_chunks} ({len(chunk)} records)")
            try:
                self._request_form(url, payload)
                logger.info(f"Log chunk {chunk_num}/{total_chunks} sent ({len(chunk)} records)")
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to send log chunk {chunk_num}: {e}")
                raise

    def project_existed(self) -> bool:
        """Check if project exists in InsightFinder."""
        url = urllib.parse.urljoin(self.config.url, API_CHECK_ADD_PROJECT)
        payload = self._build_base_payload()
        payload["operation"] = "check"

        try:
            response = self._request_form(url, payload)
            content = response.json()
            logger.debug(f"Project check response: {content}")
            exists = content.get("isProjectExist", False)
            if exists:
                logger.info(f"Project '{self.config.project_name}' exists")
            else:
                logger.info(f"Project '{self.config.project_name}' does not exist")
            return exists
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to check project '{self.config.project_name}': {e}")
            return False
        except (ValueError, KeyError) as e:
            logger.error(f"Invalid response when checking project: {e}")
            return False

    def create_custom_project(self) -> bool:
        """Create a new project in InsightFinder."""
        url = urllib.parse.urljoin(self.config.url, API_CHECK_ADD_PROJECT)
        payload = self._build_base_payload()
        payload["operation"] = "create"
        payload["systemName"] = self.config.system_name or ""
        payload["dataType"] = self.config.data_type or ""
        payload["instanceType"] = self.config.instance_type
        payload["insightAgentType"] = self.config.insight_agent_type or ""
        payload["projectCloudType"] = "PrivateCloud"
        payload["samplingInterval"] = str(self.config.sampling_interval)

        try:
            response = self._request_form(url, payload)
            content = response.json()
            logger.debug(f"Project creation response: {content}")
            success = content.get("success", False)
            if success:
                logger.info(f"Project '{self.config.project_name}' created successfully")
            else:
                logger.warning(f"Project '{self.config.project_name}' creation failed")
            return success
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create project '{self.config.project_name}': {e}")
            return False
        except (ValueError, KeyError) as e:
            logger.error(f"Invalid response when creating project: {e}")
            return False

    def _request(self, url: str, payload: dict[str, Any]) -> requests.Response:
        """POST JSON payload (v2 API)."""
        logger.debug(f"Sending request to {url}")
        headers = {"Content-Type": "application/json"}
        response = self.session.post(url, json=payload, headers=headers, verify=False, timeout=30)
        response.raise_for_status()
        return response

    def _request_form(self, url: str, payload: dict[str, str]) -> requests.Response:
        """POST form-encoded payload (v1 API)."""
        logger.debug(f"Sending request to {url}")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = self.session.post(url, data=payload, headers=headers, verify=False, timeout=30)
        response.raise_for_status()
        return response
