from __future__ import annotations

import dataclasses
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclasses.dataclass
class Config:
    # InsightFinder
    if_url: str
    if_user_name: str
    if_license_key: str
    if_project_name: str
    if_system_name: str
    if_sampling_interval: int
    if_set_component: bool

    # Jira Asset Registry
    jira_base: str
    jira_api_key: str

    # UniFi
    unifi_api_key: str | None

    # UISP
    uisp_url: str | None
    uisp_api_token: str | None

    # Mimosa
    mimosa_url: str | None
    mimosa_username: str | None
    mimosa_password: str | None
    mimosa_network_id: str | None

    # Tarana
    tarana_base_url: str | None
    tarana_username: str | None
    tarana_password: str | None
    tarana_region_ids: list[int] | None

    # Baicells
    baicells_base_url: str | None
    baicells_username: str | None
    baicells_password: str | None
    baicells_enrich_budget_seconds: int

    # NetExperience
    netexperience_base_url: str | None
    netexperience_user_id: str | None
    netexperience_password: str | None
    netexperience_service_provider_id: int | None
    netexperience_fetch_ip: bool

    # Positron
    positron_url: str | None
    positron_username: str | None
    positron_password: str | None

    # Ruckus
    ruckus_url: str | None
    ruckus_username: str | None
    ruckus_password: str | None
    ruckus_api_version: str

    # Cambium
    cambium_base_url: str | None
    cambium_email: str | None
    cambium_password: str | None

    # Telrad (BreezeVIEW CLI — CPEs only)
    telrad_breezeview_cli_host: str | None
    telrad_breezeview_cli_port: str | None
    telrad_breezeview_cli_user: str | None
    telrad_breezeview_cli_password: str | None
    telrad_breezeview_cli_snapshot_timeout: int
    telrad_breezeview_cli_poll_interval: int

    # Zabbix
    zabbix_url: str | None
    zabbix_user: str | None
    zabbix_password: str | None


def load_config(env_path: Path | None = None) -> Config:
    load_dotenv(dotenv_path=env_path or Path(__file__).parent.parent / ".env")

    def require(name: str) -> str:
        val = os.environ.get(name)
        if not val:
            raise SystemExit(f"{name} not set in .env or environment.")
        return val

    def as_bool(name: str, default: bool) -> bool:
        val = os.environ.get(name)
        if val is None:
            return default
        return val.strip().lower() not in ("false", "0", "no")

    def as_int_list(name: str) -> list[int] | None:
        val = os.environ.get(name)
        if not val:
            return None
        return [int(v.strip()) for v in val.split(",") if v.strip()]

    def as_optional_int(name: str) -> int | None:
        val = os.environ.get(name)
        return int(val) if val else None

    return Config(
        if_url=require("INSIGHTFINDER_URL"),
        if_user_name=require("INSIGHTFINDER_USER_NAME"),
        if_license_key=require("INSIGHTFINDER_LICENSE_KEY"),
        if_project_name=require("INSIGHTFINDER_PROJECT_NAME"),
        if_system_name=os.environ.get("INSIGHTFINDER_SYSTEM_NAME") or "",
        if_sampling_interval=int(os.environ.get("INSIGHTFINDER_SAMPLING_INTERVAL") or "1"),
        if_set_component=as_bool("INSIGHTFINDER_SET_COMPONENT", True),
        jira_base=require("JIRAASSET_BASE"),
        jira_api_key=require("JIRAASSET_API_KEY"),
        unifi_api_key=os.environ.get("UNIFI_API_KEY"),
        uisp_url=os.environ.get("UISP_URL"),
        uisp_api_token=os.environ.get("UISP_API_TOKEN"),
        mimosa_url=os.environ.get("MIMOSA_URL"),
        mimosa_username=os.environ.get("MIMOSA_USERNAME"),
        mimosa_password=os.environ.get("MIMOSA_PASSWORD"),
        mimosa_network_id=os.environ.get("MIMOSA_NETWORK_ID"),
        tarana_base_url=os.environ.get("TARANA_BASE_URL"),
        tarana_username=os.environ.get("TARANA_USERNAME"),
        tarana_password=os.environ.get("TARANA_PASSWORD"),
        tarana_region_ids=as_int_list("TARANA_REGION_IDS"),
        baicells_base_url=os.environ.get("BAICELLS_BASE_URL"),
        baicells_username=os.environ.get("BAICELLS_USERNAME"),
        baicells_password=os.environ.get("BAICELLS_PASSWORD"),
        baicells_enrich_budget_seconds=int(os.environ.get("BAICELLS_ENRICH_BUDGET_SECONDS") or "900"),
        netexperience_base_url=os.environ.get("NETEXPERIENCE_BASE_URL"),
        netexperience_user_id=os.environ.get("NETEXPERIENCE_USER_ID"),
        netexperience_password=os.environ.get("NETEXPERIENCE_PASSWORD"),
        netexperience_service_provider_id=as_optional_int("NETEXPERIENCE_SERVICE_PROVIDER_ID"),
        netexperience_fetch_ip=as_bool("NETEXPERIENCE_FETCH_IP", True),
        positron_url=os.environ.get("POSITRON_URL"),
        positron_username=os.environ.get("POSITRON_USERNAME"),
        positron_password=os.environ.get("POSITRON_PASSWORD"),
        ruckus_url=os.environ.get("RUCKUS_URL"),
        ruckus_username=os.environ.get("RUCKUS_USERNAME"),
        ruckus_password=os.environ.get("RUCKUS_PASSWORD"),
        ruckus_api_version=os.environ.get("RUCKUS_API_VERSION") or "v11_1",
        cambium_base_url=os.environ.get("CAMBIUM_BASE_URL"),
        cambium_email=os.environ.get("CAMBIUM_EMAIL"),
        cambium_password=os.environ.get("CAMBIUM_PASSWORD"),
        telrad_breezeview_cli_host=os.environ.get("TELRAD_BREEZEVIEW_CLI_HOST"),
        telrad_breezeview_cli_port=os.environ.get("TELRAD_BREEZEVIEW_CLI_PORT"),
        telrad_breezeview_cli_user=os.environ.get("TELRAD_BREEZEVIEW_CLI_USER"),
        telrad_breezeview_cli_password=os.environ.get("TELRAD_BREEZEVIEW_CLI_PASSWORD"),
        telrad_breezeview_cli_snapshot_timeout=int(os.environ.get("TELRAD_BREEZEVIEW_CLI_SNAPSHOT_TIMEOUT") or "240"),
        telrad_breezeview_cli_poll_interval=int(os.environ.get("TELRAD_BREEZEVIEW_CLI_POLL_INTERVAL") or "10"),
        zabbix_url=os.environ.get("ZABBIX_URL"),
        zabbix_user=os.environ.get("ZABBIX_USER"),
        zabbix_password=os.environ.get("ZABBIX_PASSWORD"),
    )
