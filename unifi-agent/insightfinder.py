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

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_METRIC_DATA_RECEIVE = "api/v2/metric-data-receive"
API_CHECK_ADD_PROJECT = "api/v1/check-and-add-custom-project"
API_CUSTOM_PROJECT_RAW_DATA = "api/v1/customprojectrawdata"
LOG_CHUNK_SIZE = 5000

logger = logging.getLogger(__name__)


def _build_session() -> requests.Session:
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
        self.session.close()

    def _build_base_payload(self) -> dict[str, str]:
        return {
            "userName": self.config.user_name,
            "licenseKey": self.config.license_key,
            "projectName": self.config.project_name,
        }

    def send_metric(self, data: dict[str, Any]) -> None:
        if not data:
            logger.warning("No data to send")
            return

        url = urllib.parse.urljoin(self.config.url, API_METRIC_DATA_RECEIVE)
        base = self._build_base_payload()
        payload = {
            "userName": base["userName"],
            "licenseKey": base["licenseKey"],
            "data": {
                "projectName": base["projectName"],
                "userName": base["userName"],
                "iat": self.config.insight_agent_type or "Custom",
                "ct": self.config.instance_type,
                "idm": data,
            },
        }

        num_instances = len(data)
        logger.info("Sending data for %d instance(s)", num_instances)
        try:
            self._request(url, payload)
            logger.info("Successfully sent data for %d instance(s)", num_instances)
        except requests.exceptions.RequestException as e:
            logger.error("Failed to send data: %s", e)
            raise

    def send_log(self, logs: list[dict[str, Any]]) -> None:
        if not logs:
            logger.warning("No log data to send")
            return

        url = urllib.parse.urljoin(self.config.url, API_CUSTOM_PROJECT_RAW_DATA)
        total_chunks = (len(logs) + LOG_CHUNK_SIZE - 1) // LOG_CHUNK_SIZE
        for chunk_num, i in enumerate(range(0, len(logs), LOG_CHUNK_SIZE), start=1):
            chunk = logs[i : i + LOG_CHUNK_SIZE]
            payload = {
                **self._build_base_payload(),
                "agentType": self.config.agent_type,
                "metricData": json.dumps(chunk),
            }
            logger.debug("Sending log chunk %d/%d (%d records)", chunk_num, total_chunks, len(chunk))
            try:
                self._request_form(url, payload)
                logger.info("Log chunk %d/%d sent (%d records)", chunk_num, total_chunks, len(chunk))
            except requests.exceptions.RequestException as e:
                logger.error("Failed to send log chunk %d: %s", chunk_num, e)
                raise

    def project_existed(self) -> bool:
        """Check if project exists in InsightFinder."""
        url = urllib.parse.urljoin(self.config.url, API_CHECK_ADD_PROJECT)
        payload = self._build_base_payload()
        payload["operation"] = "check"

        try:
            response = self._request_form(url, payload)
            content = response.json()
            logger.debug("Project check response: %s", content)
            exists = content.get("isProjectExist", False)
            if exists:
                logger.info("Project '%s' exists", self.config.project_name)
            else:
                logger.info("Project '%s' does not exist", self.config.project_name)
            return exists
        except requests.exceptions.RequestException as e:
            logger.error("Failed to check project '%s': %s", self.config.project_name, e)
            return False
        except (ValueError, KeyError) as e:
            logger.error("Invalid response when checking project: %s", e)
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
            logger.debug("Project creation response: %s", content)
            success = content.get("success", False)
            if success:
                logger.info("Project '%s' created successfully", self.config.project_name)
            else:
                logger.warning("Project '%s' creation failed", self.config.project_name)
            return success
        except requests.exceptions.RequestException as e:
            logger.error("Failed to create project '%s': %s", self.config.project_name, e)
            return False
        except (ValueError, KeyError) as e:
            logger.error("Invalid response when creating project: %s", e)
            return False

    def _request(self, url: str, payload: dict[str, Any]) -> requests.Response:
        """POST JSON payload (v2 API)."""
        logger.debug("Sending request to %s", url)
        headers = {"Content-Type": "application/json"}
        response = self.session.post(url, json=payload, headers=headers, verify=False, timeout=30)
        response.raise_for_status()
        return response

    def _request_form(self, url: str, payload: dict[str, str]) -> requests.Response:
        """POST form-encoded payload (v1 API)."""
        logger.debug("Sending request to %s", url)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = self.session.post(url, data=payload, headers=headers, verify=False, timeout=30)
        response.raise_for_status()
        return response
