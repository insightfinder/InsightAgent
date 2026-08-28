"""Controller registry. Every entry here runs by default — `--controllers`
only ever narrows the set. Add a vendor by adding one module + one factory
entry; no orchestration change needed.

Each factory takes the Config and returns a Controller instance, or None if
required credentials are absent (the caller skips it with a warning rather
than failing the whole run).
"""

from __future__ import annotations

from typing import Callable

from config import Config
from controllers.baicells import BaicellsController
from controllers.base import Controller
from controllers.cambium import CambiumController
from controllers.mimosa import MimosaController
from controllers.netexperience import NetExperienceController
from controllers.positron import PositronController
from controllers.ruckus import RuckusController
from controllers.tarana import TaranaController
from controllers.telrad import TelradController
from controllers.uisp import UispController
from controllers.unifi import UnifiController


def _build_unifi(cfg: Config) -> Controller | None:
    if not cfg.unifi_api_key:
        return None
    return UnifiController(api_key=cfg.unifi_api_key)


def _build_uisp(cfg: Config) -> Controller | None:
    if not (cfg.uisp_url and cfg.uisp_api_token):
        return None
    return UispController(
        base_url=cfg.uisp_url,
        api_token=cfg.uisp_api_token,
    )


def _build_mimosa(cfg: Config) -> Controller | None:
    if not (cfg.mimosa_url and cfg.mimosa_username and cfg.mimosa_password and cfg.mimosa_network_id):
        return None
    return MimosaController(
        base_url=cfg.mimosa_url,
        username=cfg.mimosa_username,
        password=cfg.mimosa_password,
        network_id=cfg.mimosa_network_id,
    )


def _build_positron(cfg: Config) -> Controller | None:
    if not (cfg.positron_url and cfg.positron_username and cfg.positron_password):
        return None
    return PositronController(
        base_url=cfg.positron_url,
        username=cfg.positron_username,
        password=cfg.positron_password,
    )


def _build_ruckus(cfg: Config) -> Controller | None:
    if not (cfg.ruckus_url and cfg.ruckus_username and cfg.ruckus_password):
        return None
    return RuckusController(
        base_url=cfg.ruckus_url,
        username=cfg.ruckus_username,
        password=cfg.ruckus_password,
        api_version=cfg.ruckus_api_version,
    )


def _build_tarana(cfg: Config) -> Controller | None:
    if not (cfg.tarana_base_url and cfg.tarana_username and cfg.tarana_password):
        return None
    return TaranaController(
        base_url=cfg.tarana_base_url,
        username=cfg.tarana_username,
        password=cfg.tarana_password,
        region_ids=cfg.tarana_region_ids,
    )


def _build_baicells(cfg: Config) -> Controller | None:
    if not (cfg.baicells_base_url and cfg.baicells_username and cfg.baicells_password):
        return None
    return BaicellsController(
        base_url=cfg.baicells_base_url,
        username=cfg.baicells_username,
        password=cfg.baicells_password,
        enrich_budget_seconds=cfg.baicells_enrich_budget_seconds,
    )


def _build_netexperience(cfg: Config) -> Controller | None:
    if not (
        cfg.netexperience_base_url
        and cfg.netexperience_user_id
        and cfg.netexperience_password
    ) or cfg.netexperience_service_provider_id is None:
        return None
    return NetExperienceController(
        base_url=cfg.netexperience_base_url,
        user_id=cfg.netexperience_user_id,
        password=cfg.netexperience_password,
        service_provider_id=cfg.netexperience_service_provider_id,
        fetch_ip=cfg.netexperience_fetch_ip,
    )


def _build_cambium(cfg: Config) -> Controller | None:
    if not (cfg.cambium_base_url and cfg.cambium_email and cfg.cambium_password):
        return None
    base_urls = [u.strip() for u in cfg.cambium_base_url.split(",") if u.strip()]
    return CambiumController(
        base_urls=base_urls,
        email=cfg.cambium_email,
        password=cfg.cambium_password,
    )


def _build_telrad(cfg: Config) -> Controller | None:
    if not (
        cfg.telrad_breezeview_cli_host
        and cfg.telrad_breezeview_cli_port
        and cfg.telrad_breezeview_cli_user
        and cfg.telrad_breezeview_cli_password
    ):
        return None
    return TelradController(
        host=cfg.telrad_breezeview_cli_host,
        port=cfg.telrad_breezeview_cli_port,
        user=cfg.telrad_breezeview_cli_user,
        password=cfg.telrad_breezeview_cli_password,
        snapshot_timeout=cfg.telrad_breezeview_cli_snapshot_timeout,
        poll_interval=cfg.telrad_breezeview_cli_poll_interval,
    )


# name -> factory.
CONTROLLER_FACTORIES: dict[str, Callable[[Config], Controller | None]] = {
    "baicells": _build_baicells,
    "cambium": _build_cambium,
    "mimosa": _build_mimosa,
    "netexperience": _build_netexperience,
    "positron": _build_positron,
    "ruckus": _build_ruckus,
    "tarana": _build_tarana,
    "telrad": _build_telrad,
    "uisp": _build_uisp,
    "unifi": _build_unifi,
}


def build_controllers(cfg: Config, only: list[str] | None = None) -> list[Controller]:
    names = only if only else list(CONTROLLER_FACTORIES.keys())
    controllers: list[Controller] = []
    for name in names:
        factory = CONTROLLER_FACTORIES.get(name)
        if factory is None:
            raise SystemExit(f"Unknown controller: {name!r} (known: {', '.join(CONTROLLER_FACTORIES)})")
        controller = factory(cfg)
        if controller is None:
            import logging

            logging.getLogger(__name__).warning(
                "Skipping controller %r — required credentials not set in .env", name
            )
            continue
        controllers.append(controller)
    return controllers
