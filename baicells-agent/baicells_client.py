#!/usr/bin/env python3

"""
BaiCells OMC API Client
Provides methods to interact with BaiCells OMC RESTful API for device management.
"""

import os
import time
import logging
import requests
from typing import Any
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class BaiCellsClient:
    """Client for BaiCells OMC RESTful API operations."""

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: int = 10,
    ):
        """
        Initialize BaiCells API client.

        Args:
            base_url: Base URL for API (defaults to env var BAICELLS_BASE_URL)
            username: API username (defaults to env var BAICELLS_USERNAME)
            password: API password (defaults to env var BAICELLS_PASSWORD)
            timeout: Request timeout in seconds
        """
        load_dotenv()

        # Support both BAICELLS_BASE_URL and BAICELLS_URL for compatibility
        self.base_url = (
            base_url
            or os.getenv("BAICELLS_BASE_URL")
            or os.getenv("BAICELLS_URL", "https://cloudcore.baicells.com:7085")
        )
        self.username = username or os.getenv("BAICELLS_USERNAME")
        self.password = password or os.getenv("BAICELLS_PASSWORD")
        self.timeout = timeout

        self.token: str | None = None
        self.token_expires_at: float = 0

        if not self.username or not self.password:
            raise ValueError(
                "Username and password are required (set in .env or pass to constructor)"
            )

    def _is_token_valid(self) -> bool:
        """Check if current token is valid and not expired."""
        if not self.token:
            return False
        # Refresh token 5 minute before expiry to avoid edge cases
        return time.time() < (self.token_expires_at - 300)

    def authenticate(self) -> str:
        """
        Authenticate and get access token.

        Returns:
            Access token string

        Raises:
            Exception: If authentication fails
        """
        if self._is_token_valid():
            return self.token

        endpoint = f"{self.base_url}/northboundApi/v1/access/token"
        payload = {"username": self.username, "password": self.password}
        headers = {"Content-Type": "application/json;charset=UTF-8"}

        try:
            response = requests.post(
                endpoint, json=payload, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            if data.get("code") not in (0, 200):
                raise Exception(
                    f"Authentication failed: {data.get('message', 'Unknown error')}"
                )

            self.token = data.get("data", {}).get("token")
            expires_in = data.get("data", {}).get("expires", 1800)
            self.token_expires_at = time.time() + expires_in

            if not self.token:
                raise Exception("No token received from authentication response")

            return self.token

        except requests.RequestException as e:
            raise Exception(f"Authentication request failed: {e}")

    def _get_headers(self) -> dict[str, str]:
        """Get headers with valid authentication token."""
        token = self.authenticate()  # Will reuse valid token or get new one
        return {
            "Authorization": token,
            "Content-Type": "application/json;charset=UTF-8",
        }

    def get_all_groups(self, search_text: str | None = None) -> list[dict[str, Any]]:
        """
        Get all device groups with hierarchical structure flattened.

        Args:
            search_text: Optional search filter

        Returns:
            List of group dictionaries with keys: id, name, description, built_in, parent_name
        """
        endpoint = f"{self.base_url}/northboundApi/v1/device/group"
        headers = self._get_headers()

        params = {}
        if search_text:
            params["searchText"] = search_text

        try:
            response = requests.get(
                endpoint, headers=headers, params=params, timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            if data.get("code") not in (0, 200):
                raise Exception(
                    f"Get groups failed: {data.get('message', 'Unknown error')}"
                )

            groups_data = data.get("data", {})
            rows = groups_data.get("rows", [])

            # Flatten hierarchical structure
            all_groups = []
            self._flatten_groups(rows, all_groups, parent_name=None)

            return all_groups

        except requests.RequestException as e:
            raise Exception(f"Get groups request failed: {e}")

    def _flatten_groups(
        self, groups: list[dict], result: list[dict], parent_name: str | None = None
    ):
        """
        Recursively flatten hierarchical group structure.

        Args:
            groups: List of group dictionaries
            result: Accumulator list for flattened groups
            parent_name: Parent group name for hierarchy tracking
        """
        for group in groups:
            group_info = {
                "id": group.get("id"),
                "name": group.get("group_name"),
                "description": group.get("description"),
                "built_in": group.get("built_in"),
                "parent_name": parent_name,
            }
            result.append(group_info)

            # Recursively process children
            children = group.get("children", [])
            if children:
                self._flatten_groups(
                    children, result, parent_name=group.get("group_name")
                )

    def get_devices_by_group(
        self, group_id: int, page_size: int = 100, search_text: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Get all devices for a specific group (with pagination handling).

        Args:
            group_id: Group ID (must be integer)
            page_size: Number of devices per page
            search_text: Optional search filter

        Returns:
            List of device dictionaries
        """
        return self._get_devices_by_group(
            group_id, page_size=page_size, search_text=search_text
        )

    def get_cpes_by_group(
        self,
        group_id: int,
        page_size: int = 100,
        search_text: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get all CPE devices for a specific group.

        CPE devices are identified by validating against the CPE info endpoint.
        This queries all devices and validates each one.

        Args:
            group_id: Group ID (must be integer)
            page_size: Number of devices per page
            search_text: Optional search filter

        Returns:
            List of CPE device dictionaries
        """
        # Query all devices
        all_devices = self._get_devices_by_group(
            group_id, page_size=page_size, search_text=search_text
        )

        logger.info(
            f"  → Found {len(all_devices)} total device(s) in group, validating CPE..."
        )

        # Validate each device by trying to get CPE info
        cpe_devices = []
        for device in all_devices:
            serial_number = device.get("serial_number")
            if serial_number:
                logger.debug(f"    → Checking device {serial_number}...")
                try:
                    # If get_cpe_info succeeds, it's a CPE device
                    self.get_cpe_info(serial_number)
                    cpe_devices.append(device)
                    logger.info(f"    ✓ {serial_number}: Valid CPE device")
                except Exception as e:
                    # Not a CPE device - validation failed
                    error_msg = str(e)
                    logger.debug(f"    ✗ {serial_number}: {error_msg}")
                    pass

        return cpe_devices

    def _get_devices_by_group(
        self,
        group_id: int,
        page_size: int = 100,
        search_text: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get all devices for a specific group (with pagination handling).

        Note: isGnb is fixed to 0 for this endpoint.

        Args:
            group_id: Group ID (must be integer)
            page_size: Number of devices per page
            search_text: Optional search filter

        Returns:
            List of device dictionaries
        """
        endpoint = f"{self.base_url}/northboundApi/v1/device/query"
        headers = self._get_headers()

        all_devices = []
        page_no = 0

        while True:
            payload = {
                "isGnb": 0,
                "groupId": int(group_id),
                "searchText": search_text,
                "pageSize": page_size,
                "pageNo": page_no,
            }

            try:
                response = requests.post(
                    endpoint, json=payload, headers=headers, timeout=self.timeout
                )
                response.raise_for_status()

                data = response.json()
                if data.get("code") not in (0, 200):
                    raise Exception(
                        f"Get devices failed: {data.get('message', 'Unknown error')}"
                    )

                result_data = data.get("data", {})
                devices = result_data.get("rows", [])
                total = result_data.get("total", 0)

                all_devices.extend(devices)

                # Check if we have all devices
                if len(all_devices) >= total or len(devices) == 0:
                    break

                page_no += 1

            except requests.RequestException as e:
                raise Exception(
                    f"Get devices request failed for group {group_id}, page {page_no}: {e}"
                )

        return all_devices

    def get_all_cpes(self, page_size: int = 100) -> dict[str, Any]:
        """
        Get all CPE devices from all groups.

        CPE devices are identified by validating against the CPE info endpoint.
        This may take some time as it validates each device.

        Args:
            page_size: Number of devices per page for pagination

        Returns:
            Dictionary containing:
                - groups: List of all groups
                - devices_by_group: Dictionary mapping group_id to list of CPE devices
                - all_devices: Flattened list of all CPE devices
                - summary: Statistics about groups and devices
        """
        logger.info("Fetching all groups...")
        groups = self.get_all_groups()

        # Filter to only integer group IDs (children/leaf groups that can query devices)
        queryable_groups = [g for g in groups if isinstance(g["id"], int)]

        logger.info(
            f"Found {len(groups)} total groups ({len(queryable_groups)} queryable)"
        )
        logger.info("Validating devices against CPE endpoint...")

        devices_by_group = {}
        all_devices = []

        for idx, group in enumerate(queryable_groups, 1):
            group_id = group["id"]
            group_name = group["name"]

            logger.info(
                f"[{idx}/{len(queryable_groups)}] Checking group '{group_name}' (ID: {group_id})..."
            )

            try:
                devices = self.get_cpes_by_group(group_id, page_size=page_size)
                devices_by_group[group_id] = devices
                all_devices.extend(devices)

                if devices:
                    logger.info(f"  → Found {len(devices)} CPE device(s)")
                else:
                    logger.info("  → No CPE devices found in this group")

            except Exception as e:
                logger.error(f"  → Error: {e}")
                devices_by_group[group_id] = []

        summary = {
            "total_groups": len(groups),
            "queryable_groups": len(queryable_groups),
            "total_devices": len(all_devices),
            "groups_with_devices": sum(
                1 for devices in devices_by_group.values() if devices
            ),
            "online_devices": sum(
                1 for d in all_devices if d.get("connection_status", "").lower() == "on"
            ),
        }

        return {
            "groups": groups,
            "devices_by_group": devices_by_group,
            "all_devices": all_devices,
            "summary": summary,
        }

    def get_all_devices(self, page_size: int = 100) -> dict[str, Any]:
        """
        Get all devices from all groups.

        Args:
            page_size: Number of devices per page for pagination

        Returns:
            Dictionary containing:
                - groups: List of all groups
                - devices_by_group: Dictionary mapping group_id to list of devices
                - all_devices: Flattened list of all devices
                - summary: Statistics about groups and devices
        """
        logger.info("Fetching all groups...")
        groups = self.get_all_groups()

        # Filter to only integer group IDs (children/leaf groups that can query devices)
        queryable_groups = [g for g in groups if isinstance(g["id"], int)]

        logger.info(
            f"Found {len(groups)} total groups ({len(queryable_groups)} queryable)"
        )

        devices_by_group = {}
        all_devices = []

        for idx, group in enumerate(queryable_groups, 1):
            group_id = group["id"]
            group_name = group["name"]

            logger.info(
                f"[{idx}/{len(queryable_groups)}] Fetching devices for group '{group_name}' (ID: {group_id})..."
            )

            try:
                devices = self.get_devices_by_group(group_id, page_size=page_size)
                devices_by_group[group_id] = devices
                all_devices.extend(devices)

                logger.info(f"  → Found {len(devices)} devices")

            except Exception as e:
                logger.error(f"  → Error: {e}")
                devices_by_group[group_id] = []

        summary = {
            "total_groups": len(groups),
            "queryable_groups": len(queryable_groups),
            "total_devices": len(all_devices),
            "groups_with_devices": sum(
                1 for devices in devices_by_group.values() if devices
            ),
            "online_devices": sum(
                1 for d in all_devices if d.get("connection_status", "").lower() == "on"
            ),
        }

        return {
            "groups": groups,
            "devices_by_group": devices_by_group,
            "all_devices": all_devices,
            "summary": summary,
        }

    def get_enb_status(self, serial_number: str) -> dict[str, Any]:
        """
        Get running status of a specific eNB device.

        Args:
            serial_number: eNB device serial number

        Returns:
            eNB status dictionary
        """
        endpoint = (
            f"{self.base_url}/northboundApi/v1/enodeb/infos/status/{serial_number}"
        )
        headers = self._get_headers()

        try:
            response = requests.get(endpoint, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()
            if data.get("code") not in (0, 200):
                raise Exception(
                    f"Get eNB status failed: {data.get('message', 'Unknown error')}"
                )

            return data.get("data", {})

        except requests.RequestException as e:
            raise Exception(f"Get eNB status request failed: {e}")

    def get_cpe_status(self, serial_number: str) -> dict[str, Any]:
        """
        Get CPE (Customer Premises Equipment) connection status.

        Args:
            serial_number: CPE serial number

        Returns:
            CPE status dictionary with connection_status, serialNumber
        """
        endpoint = f"{self.base_url}/v1/cpe/status/{serial_number}"
        headers = self._get_headers()

        try:
            response = requests.get(endpoint, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()
            if data.get("code") not in (0, 200):
                raise Exception(
                    f"Get CPE status failed: {data.get('message', 'Unknown error')}"
                )

            return data.get("data", {})

        except requests.RequestException as e:
            raise Exception(f"Get CPE status request failed: {e}")

    def get_cpe_info(self, serial_number: str) -> dict[str, Any]:
        """
        Get detailed CPE information including signal quality metrics.

        This endpoint provides radio signal metrics like RSRP, RSRQ, SINR, CINR
        for both LTE and 5G NR connections.

        Args:
            serial_number: CPE serial number

        Returns:
            CPE info dictionary with fields including:
            - Signal metrics: rsrp0, rsrp1, cpeSinr, cinr0, cinr1
            - 5G metrics: nrRsrp, nrRsrq, nrSinr, nrCinr
            - Network info: bandwidth, mcc, mnc, pci, cellIdentity
            - Performance: dlCurrentDataRate, ulCurrentDataRate, txPower
            - Status: connectionStatus, lteStatus, onlineTime, offlineTime
        """
        endpoint = f"{self.base_url}/northboundApi/v1/cpe/infos/{serial_number}"
        headers = self._get_headers()

        try:
            response = requests.get(endpoint, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()
            if data.get("code") not in (0, 200):
                raise Exception(
                    f"Get CPE info failed: {data.get('message', 'Unknown error')}"
                )

            return data.get("data", {})

        except requests.RequestException as e:
            raise Exception(f"Get CPE info request failed: {e}")
