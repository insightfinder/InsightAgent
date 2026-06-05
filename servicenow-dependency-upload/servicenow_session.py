#!/usr/bin/env python3
"""
Builds an authenticated requests.Session for the ServiceNow REST API.

Supports two auth methods, selected by config.servicenow_auth_method:
  - "basic": HTTP Basic Auth (servicenow_user / servicenow_password)
  - "oauth": OAuth 2.0 Resource Owner Password Credentials grant. Exchanges
             client_id/client_secret + username/password at /oauth_token.do for
             a Bearer access token, then attaches it to every request.

The rest of the pipeline just calls get_servicenow_session() and uses the
returned session, so switching auth methods needs no other code changes.
"""

import logging
import requests
import config

logger = logging.getLogger(__name__)


def _fetch_oauth_token():
    """Exchange credentials for an OAuth access token via /oauth_token.do."""
    url = f"{config.servicenow_url.rstrip('/')}/oauth_token.do"
    data = {
        "grant_type": "password",
        "client_id": config.servicenow_oauth_client_id,
        "client_secret": config.servicenow_oauth_client_secret,
        "username": config.servicenow_user,
        "password": config.servicenow_password,
    }

    missing = [k for k in ("servicenow_oauth_client_id", "servicenow_oauth_client_secret")
               if not getattr(config, k, "")]
    if missing:
        raise ValueError(
            f"OAuth auth selected but {', '.join(missing)} not set in config.py. "
            f"Ask your ServiceNow admin to register an OAuth API endpoint "
            f"(System OAuth > Application Registry) to get these values."
        )

    resp = requests.post(
        url,
        data=data,
        headers={"Accept": "application/json"},
        timeout=60,
    )
    if resp.status_code != 200:
        logger.error(f"OAuth token request failed: HTTP {resp.status_code}")
        logger.error(f"Response: {resp.text}")
        resp.raise_for_status()

    token = resp.json().get("access_token")
    if not token:
        raise ValueError(f"OAuth token response had no access_token: {resp.text}")
    return token


def get_servicenow_session():
    """Return a requests.Session pre-configured with the chosen auth method."""
    method = getattr(config, "servicenow_auth_method", "basic").lower()
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    if method == "oauth":
        token = _fetch_oauth_token()
        session.headers["Authorization"] = f"Bearer {token}"
        logger.info("ServiceNow auth method: OAuth 2.0 (Bearer token acquired)")
    else:
        session.auth = (config.servicenow_user, config.servicenow_password)
        logger.info("ServiceNow auth method: Basic")

    return session
