#!/usr/bin/env python3
"""OAuth2 / Basic Auth session factory for the ServiceNow ticket collector.

Standalone module -- it does not import anything from getmessages_servicenow,
so it can be unit-tested (and reasoned about) without the rest of the agent.

Why a disk-backed cache is required, not just an in-process one:
  - cron.py re-execs the whole script every `run_interval` (see cron.py:14-19
    in the reference elasticsearch_collector template), so an in-process
    cache buys nothing across runs.
  - main() forks N collector processes, so an in-process cache buys nothing
    across siblings either.
A TokenStore therefore persists to disk and can optionally be backed by a
multiprocessing.Manager().dict() so siblings within one run see each other's
refreshes immediately.
"""
import hashlib
import json
import os
import time

import requests
import requests.auth

# Seconds before a token's real expiry that a caller should treat it as
# already-expired and refresh proactively.
SNOW_TOKEN_REFRESH_MARGIN = 120

# ServiceNow access tokens default to 30 minutes; used only as a fallback
# when a token response omits expires_in (should not normally happen).
DEFAULT_TOKEN_TTL_SECONDS = 1800


class AuthError(Exception):
    """Raised when a token fetch or refresh grant fails."""


def make_cache_key(base_url, grant_type, client_id, username, config_basename):
    """Builds a short, stable cache key that is unique per (instance, config).

    This is the direct fix for the legacy servicenow agent's CWD-relative
    `status` watermark file, which silently collided whenever two agent
    instances were launched from the same working directory.
    """
    raw = '|'.join([base_url or '', grant_type or '', client_id or '',
                    username or '', config_basename or ''])
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]


class TokenStore:
    """Disk-backed token cache, optionally mirrored in a shared in-run dict."""

    def __init__(self, state_dir, cache_key, shared_dict=None):
        self.state_dir = state_dir
        self.cache_key = cache_key
        self.path = os.path.join(state_dir, 'token_{}.json'.format(cache_key))
        self.shared_dict = shared_dict

    def read(self):
        """Returns the cached token dict, or None. Prefers the shared cache
        (fresher: a sibling may have refreshed since this file was last
        read), falling back to disk."""
        if self.shared_dict is not None and self.cache_key in self.shared_dict:
            return self.shared_dict[self.cache_key]
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path) as f:
                tok = json.load(f)
        except (OSError, ValueError):
            return None
        if self.shared_dict is not None:
            self.shared_dict[self.cache_key] = tok
        return tok

    def write(self, tok):
        """Atomically persists tok to disk (mode 0600) and publishes it to
        the shared cache. Returns tok for chaining."""
        os.makedirs(self.state_dir, exist_ok=True)
        tmp_path = '{}.tmp.{}'.format(self.path, os.getpid())
        fd = os.open(tmp_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(tok, f)
        os.replace(tmp_path, self.path)
        if self.shared_dict is not None:
            self.shared_dict[self.cache_key] = tok
        return tok

    def invalidate(self):
        """Drops the cached token everywhere. Called on a 401 or a failed
        refresh, so the next ensure_token() performs a full grant."""
        if self.shared_dict is not None:
            self.shared_dict.pop(self.cache_key, None)
        try:
            os.remove(self.path)
        except OSError:
            pass


class ServiceNowAuth:
    """Acquires and refreshes OAuth2 tokens against a ServiceNow instance.

    Only the password grant is supported -- client_credentials needs an
    OAuth Entity Profile most instances don't have enabled, and no scope is
    sent, since neither is needed against any known ServiceNow instance.

    cfg keys consumed (secrets are read from the environment by the caller --
    this module never logs a request or response body, since either may
    contain the client secret or password): base_url, oauth_token_path,
    oauth_client_id, oauth_client_secret, oauth_username, oauth_password.
    """

    def __init__(self, cfg, token_store, logger, session=None):
        self.cfg = cfg
        self.token_store = token_store
        self.logger = logger
        self.session = session or requests.Session()

    def _token_url(self):
        return self.cfg['base_url'].rstrip('/') + self.cfg['oauth_token_path']

    def fetch_token(self):
        """Password grant -- the only grant type this agent supports."""
        cfg = self.cfg
        data = {
            'grant_type': 'password',
            'client_id': cfg['oauth_client_id'],
            'client_secret': cfg['oauth_client_secret'],
            'username': cfg['oauth_username'],
            'password': cfg['oauth_password'],
        }
        return self._post_token(data, 'fetch')

    def refresh_token(self, refresh_token):
        data = {
            'grant_type': 'refresh_token',
            'client_id': self.cfg['oauth_client_id'],
            'client_secret': self.cfg['oauth_client_secret'],
            'refresh_token': refresh_token,
        }
        return self._post_token(data, 'refresh')

    def _post_token(self, data, what):
        try:
            r = self.session.post(self._token_url(), data=data, timeout=30)
        except requests.RequestException as e:
            raise AuthError('OAuth {} request failed: {}'.format(what, e))
        if r.status_code != 200:
            err_desc = None
            try:
                err_desc = r.json().get('error_description')
            except ValueError:
                pass
            # Deliberately do not log r.text or the request body -- either
            # may echo back the client secret or password.
            self.logger.error(
                'OAuth %s failed: HTTP %d%s', what, r.status_code,
                ' ({})'.format(err_desc) if err_desc else '')
            raise AuthError('OAuth {} failed with HTTP {}'.format(what, r.status_code))
        try:
            body = r.json()
        except ValueError:
            raise AuthError('OAuth {} returned a non-JSON response'.format(what))
        if 'access_token' not in body:
            raise AuthError('OAuth {} response missing access_token'.format(what))
        now = time.time()
        return {
            'access_token': body['access_token'],
            'refresh_token': body.get('refresh_token'),
            'expires_at': now + float(body.get('expires_in', DEFAULT_TOKEN_TTL_SECONDS)),
        }

    def ensure_token(self, margin_seconds=SNOW_TOKEN_REFRESH_MARGIN):
        """Returns a usable access token: cached-and-fresh -> as-is;
        cached-with-refresh-token -> refresh; else -> a full grant."""
        tok = self.token_store.read()
        now = time.time()
        if tok and tok.get('access_token') and tok.get('expires_at', 0) - margin_seconds > now:
            return tok['access_token']
        if tok and tok.get('refresh_token'):
            try:
                return self.token_store.write(self.refresh_token(tok['refresh_token']))['access_token']
            except AuthError as e:
                self.logger.warning('OAuth refresh failed (%s); falling back to a full grant', e)
                self.token_store.invalidate()
        return self.token_store.write(self.fetch_token())['access_token']

    def invalidate(self):
        self.token_store.invalidate()


class _BearerAuth(requests.auth.AuthBase):
    """requests auth hook that re-reads the (possibly shared) token cache on
    every request, so a sibling process's refresh-on-401 is picked up
    automatically without any extra IPC beyond the shared dict."""

    def __init__(self, auth, margin_seconds=SNOW_TOKEN_REFRESH_MARGIN):
        self._auth = auth
        self._margin = margin_seconds

    def __call__(self, request):
        request.headers['Authorization'] = 'Bearer ' + self._auth.ensure_token(self._margin)
        return request


def build_session(cfg, token_store, logger):
    """Builds a requests.Session configured per the [servicenow] connection
    settings. cfg keys: base_url, auth_type ('oauth2'|'basic'), the oauth_*
    keys consumed by ServiceNowAuth, username/password (decoded, for
    auth_type=basic), verify_certs, ca_certs, proxies (dict or None).

    The returned session's `auth` is a _BearerAuth (oauth2) or a plain
    (username, password) tuple (basic). For oauth2, the underlying
    ServiceNowAuth is also attached as session.servicenow_auth so a caller
    can invalidate() it after an HTTP 401 and retry once.
    """
    session = requests.Session()
    session.headers.update({'Accept': 'application/json'})
    if cfg.get('proxies'):
        session.proxies.update(cfg['proxies'])
    session.verify = cfg['ca_certs'] if cfg.get('ca_certs') else bool(cfg.get('verify_certs', True))

    if cfg.get('auth_type') == 'basic':
        session.auth = (cfg['username'], cfg['password'])
        session.servicenow_auth = None
    else:
        auth = ServiceNowAuth(cfg, token_store, logger)
        session.auth = _BearerAuth(auth)
        session.servicenow_auth = auth
    return session
