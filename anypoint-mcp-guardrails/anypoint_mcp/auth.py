"""Anypoint Platform OAuth2 authentication.

Uses the client_credentials flow (Connected App) to obtain a Bearer token.
The token is cached in-process and automatically refreshed when it expires
or when the server returns HTTP 401.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from anypoint_mcp.config import AnypointConfig

logger = logging.getLogger(__name__)

# Module-level token cache: { (client_id) -> (access_token, expires_at) }
_token_cache: dict[str, tuple[str, float]] = {}

# Refresh the token this many seconds before it actually expires
_EXPIRY_BUFFER_SECS = 60


def get_bearer_token(config: "AnypointConfig", force_refresh: bool = False) -> str:
    """Return a valid Bearer token, fetching a new one if needed."""
    cache_key = config.client_id
    now = time.monotonic()

    if not force_refresh and cache_key in _token_cache:
        token, expires_at = _token_cache[cache_key]
        if now < expires_at:
            return token

    token, expires_in = _fetch_token(config)
    _token_cache[cache_key] = (token, now + expires_in - _EXPIRY_BUFFER_SECS)
    return token


def _fetch_token(config: "AnypointConfig") -> tuple[str, int]:
    """POST to Anypoint token endpoint and return (access_token, expires_in)."""
    url = f"{config.base_url}/accounts/api/v2/oauth2/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": config.client_id,
        "client_secret": config.client_secret,
    }
    try:
        resp = requests.post(url, data=payload, timeout=config.http_timeout)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        raise AuthError(
            f"Token request failed: HTTP {exc.response.status_code} — {exc.response.text[:200]}"
        ) from exc
    except requests.RequestException as exc:
        raise AuthError(f"Token request failed: {exc}") from exc

    data = resp.json()
    token = data.get("access_token")
    expires_in = int(data.get("expires_in", 3600))

    if not token:
        raise AuthError(f"No access_token in response: {data}")

    logger.debug("Obtained new Bearer token (expires_in=%ds)", expires_in)
    return token, expires_in


def create_session(config: "AnypointConfig") -> requests.Session:
    """Create a requests.Session pre-loaded with a valid Bearer token."""
    session = requests.Session()
    _refresh_session_token(session, config)
    return session


def _refresh_session_token(session: requests.Session, config: "AnypointConfig") -> None:
    token = get_bearer_token(config)
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })


def refresh_session_on_401(
    session: requests.Session,
    config: "AnypointConfig",
    response: requests.Response,
) -> bool:
    """If response is 401, force-refresh the token and update the session.

    Returns True if the token was refreshed (caller should retry the request).
    """
    if response.status_code == 401:
        logger.info("Received 401 — refreshing Bearer token")
        token = get_bearer_token(config, force_refresh=True)
        session.headers.update({"Authorization": f"Bearer {token}"})
        return True
    return False


class AuthError(RuntimeError):
    """Raised when authentication fails."""
