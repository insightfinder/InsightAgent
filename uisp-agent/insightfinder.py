from __future__ import annotations

import logging
import sys
import time
import urllib.parse
import dataclasses
from functools import wraps
from typing import TypeAlias, TypedDict, Callable, Any, Iterator, TypeVar, ParamSpec

import requests
import urllib3

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

Log = TypedDict("Log", {"timestamp": str, "tag": str, "data": str | dict[str, str]})
Metric: TypeAlias = dict[str, str]
MetricData: TypeAlias = list[Log | Metric]

P = ParamSpec("P")
T = TypeVar("T")


def chunks_by_size(
    items: list[Any], max_size: int, get_size: Callable[[Any], int] = sys.getsizeof
) -> Iterator[list[Any]]:
    """Split items into chunks based on size limit.

    Args:
        items: List of items to chunk
        max_size: Maximum size per chunk in bytes
        get_size: Function to calculate item size (defaults to sys.getsizeof)

    Yields:
        Lists of items where total size <= max_size
    """
    buffer: list[Any] = []
    buffer_size = 0

    for item in items:
        item_size = get_size(item)

        # If single item exceeds max_size, yield it alone with warning
        if item_size > max_size:
            if buffer:
                yield buffer
                buffer = []
                buffer_size = 0
            logging.warning(
                f"Single item size ({item_size}) exceeds max_size ({max_size})"
            )
            yield [item]
            continue

        # If adding item would exceed limit, yield current buffer first
        if buffer_size + item_size > max_size:
            if buffer:
                yield buffer
            buffer = [item]
            buffer_size = item_size
        else:
            buffer.append(item)
            buffer_size += item_size

    # Yield remaining items
    if buffer:
        yield buffer


def retry(
    ExceptionToCheck: type[Exception] | tuple[type[Exception], ...],
    tries: int = 4,
    delay: int = 3,
    backoff: int = 2,
    logger: logging.Logger | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Retry calling the decorated function using an exponential backoff.

    :param ExceptionToCheck: the exception to check. may be a tuple of
        exceptions to check
    :type ExceptionToCheck: Exception or tuple
    :param tries: number of times to try (not retry) before giving up
    :type tries: int
    :param delay: initial delay between retries in seconds
    :type delay: int
    :param backoff: backoff multiplier e.g. value of 2 will double the delay
        each retry
    :type backoff: int
    :param logger: logger to use. If None, print
    :type logger: logging.Logger instance
    """

    def deco_retry(f: Callable[P, T]) -> Callable[P, T]:
        @wraps(f)
        def f_retry(*args: P.args, **kwargs: P.kwargs) -> T:
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck as e:
                    msg = f"{e}, Retrying in {mdelay} seconds..."
                    if logger:
                        logger.warning(msg)
                    else:
                        print(msg)
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)

        return f_retry

    return deco_retry


# API endpoint constants
API_METRIC_DATA_RECEIVE = "api/v2/metric-data-receive"
API_CHECK_ADD_PROJECT = "api/v1/check-and-add-custom-project"

# agent_type:
# "custom" for metric streaming.
# "MetricFileReplay" for metric replay.
# "LogStreaming" for log/alert streaming.
# "LogFileReplay" for log/alert replay.
#
# data_type:
# Metric, Log, Alert, Deployment, Incident.
#
# insight_agent_type:
## For metric project, it can be Custom, MetricFile, containerStreaming, containerReplay
## For log project, it can be Custom, Historical, ContainerCustom, ContainerHistorical

logger = logging.getLogger(__name__)


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
    samplingInterval: int = 600


class InsightFinder:
    """Client for interacting with InsightFinder API."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = requests.Session()
        # Don't set default Content-Type - set per request instead

        if self.config.create_project and not self.project_existed():
            self.create_custom_project()

    def __enter__(self) -> "InsightFinder":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - close session."""
        self.close()

    def close(self) -> None:
        """Close the requests session."""
        if self.session:
            self.session.close()

    def _build_base_payload(self) -> dict[str, str]:
        """Build base payload with authentication credentials."""
        return {
            "userName": self.config.user_name,
            "licenseKey": self.config.license_key,
            "projectName": self.config.project_name,
        }

    def _send_data(self, data: dict[str, Any]) -> None:
        """Common method to send data to InsightFinder v2 API.

        Args:
            data: Nested data structure in v2 format with idm (instance data map)
        """
        if not data:
            logger.warning("No data to send")
            return

        url = urllib.parse.urljoin(self.config.url, API_METRIC_DATA_RECEIVE)

        # Build v2 API payload structure
        payload = {
            "userName": self.config.user_name,
            "licenseKey": self.config.license_key,
            "data": {
                "projectName": self.config.project_name,
                "userName": self.config.user_name,
                "iat": self.config.agent_type,
                "ct": self.config.instance_type,
                "idm": data,  # Instance data map with nested structure
            },
        }

        # Count total instances for logging
        num_instances = len(data)
        logger.info(f"Sending data for {num_instances} instance(s)")

        try:
            self._request(url, payload)
            logger.info(f"Successfully sent data for {num_instances} instance(s)")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send data: {e}")
            raise

    def send_metric(self, data: dict[str, Any]) -> None:
        """Send metric data to InsightFinder v2 API.

        Args:
            data: Nested metric data in v2 format (idm structure)
        """
        self._send_data(data)

    def send_log(self, data: list[dict[str, Any]]) -> None:
        """Send log data to InsightFinder.

        Note: Log data still uses v1 API. This method is not updated for v2.

        Args:
            data: List of log data points
        """
        raise NotImplementedError(
            "send_log() is not implemented for v2 API. "
            "Log data ingestion may use a different v2 endpoint."
        )

    def send(
        self,
        data: dict[str, Any] | list[dict[str, Any]],
        instance_name: str | None = None,
    ) -> None:
        """Send data to InsightFinder (backward compatibility - deprecated).

        Note: This method signature has changed with v2 API migration.
        Use send_metric() directly with v2 format data.

        Args:
            data: Data in v2 format (dict with idm structure) for metrics
            instance_name: Deprecated parameter (not used in v2)
        """
        if self.config.agent_type in ["custom", "MetricFileReplay"]:
            if isinstance(data, dict):
                self.send_metric(data)
            else:
                raise ValueError(
                    "Metric data must be in v2 format (dict with idm structure). "
                    "Use transform_all_devices() to convert to v2 format."
                )
        else:
            raise NotImplementedError("Log/alert data not implemented for v2 API")

    def project_existed(self) -> bool:
        """Check if project exists in InsightFinder.

        Returns:
            True if project exists, False otherwise
        """
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
        """Create a new project in InsightFinder.

        Returns:
            True if project was created successfully, False otherwise
        """
        url = urllib.parse.urljoin(self.config.url, API_CHECK_ADD_PROJECT)
        payload = self._build_base_payload()
        payload["operation"] = "create"
        payload["systemName"] = self.config.system_name or ""
        payload["dataType"] = self.config.data_type or ""
        payload["instanceType"] = self.config.instance_type
        payload["insightAgentType"] = self.config.insight_agent_type or ""
        payload["projectCloudType"] = "PrivateCloud"
        payload["samplingInterval"] = str(self.config.samplingInterval)

        try:
            response = self._request_form(url, payload)
            content = response.json()
            logger.debug(f"Project creation response: {content}")

            success = content.get("success", False)
            if success:
                logger.info(
                    f"Project '{self.config.project_name}' created successfully"
                )
            else:
                logger.warning(f"Project '{self.config.project_name}' creation failed")
            return success

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create project '{self.config.project_name}': {e}")
            return False
        except (ValueError, KeyError) as e:
            logger.error(f"Invalid response when creating project: {e}")
            return False

    @retry(requests.exceptions.RequestException, tries=3, logger=logger)
    def _request(self, url: str, payload: dict[str, Any]) -> requests.Response:
        """Make HTTP POST request with retry logic (JSON format for v2 API).

        Args:
            url: Target URL
            payload: Request payload (will be sent as JSON)

        Returns:
            Response object

        Raises:
            requests.exceptions.RequestException: If request fails after retries
        """
        logger.debug(f"Sending request to {url}")
        headers = {"Content-Type": "application/json"}
        response = self.session.post(
            url, json=payload, headers=headers, verify=False, timeout=30
        )
        response.raise_for_status()
        return response

    @retry(requests.exceptions.RequestException, tries=3, logger=logger)
    def _request_form(self, url: str, payload: dict[str, str]) -> requests.Response:
        """Make HTTP POST request with form-encoded data (for v1 API).

        Args:
            url: Target URL
            payload: Request payload (will be sent as form data)

        Returns:
            Response object

        Raises:
            requests.exceptions.RequestException: If request fails after retries
        """
        logger.debug(f"Sending request to {url}")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = self.session.post(
            url, data=payload, headers=headers, verify=False, timeout=30
        )
        response.raise_for_status()
        return response
