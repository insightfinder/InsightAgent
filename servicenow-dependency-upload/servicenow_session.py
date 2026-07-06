#!/usr/bin/env python3
"""
Builds an authenticated requests.Session for the ServiceNow REST API using
HTTP Basic Auth (servicenow_user / servicenow_password).

The rest of the pipeline calls get_servicenow_session() and uses the returned
session, so auth setup lives in one place.
"""

import logging
import requests
import config

logger = logging.getLogger(__name__)


def get_servicenow_session():
    """Return a requests.Session pre-configured with Basic Auth."""
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    session.auth = (config.servicenow_user, config.servicenow_password)
    logger.info("ServiceNow auth method: Basic")
    return session
