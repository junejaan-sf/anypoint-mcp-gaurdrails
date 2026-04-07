"""CloudHub 2.0 REST API client (read-only).

Lists deployed applications in the configured Integrations-NA / Design environment.
All calls are gated through the guardrail layer before hitting the Anypoint API.
"""

from __future__ import annotations

import logging

import requests

from anypoint_mcp.auth import create_session, refresh_session_on_401
from anypoint_mcp.config import AnypointConfig
from anypoint_mcp.cloudhub.models import CloudHubApp
from anypoint_mcp.guardrails import enforce_env_scope, enforce_result_cap

logger = logging.getLogger(__name__)

_MAX_RETRY_401 = 1


class CloudHubClient:
    """Authenticated, read-only CloudHub 2.0 client."""

    def __init__(
        self,
        session: requests.Session,
        config: AnypointConfig,
    ) -> None:
        self._session = session
        self._config = config

    @classmethod
    def from_config(cls, config: AnypointConfig) -> "CloudHubClient":
        session = create_session(config)
        return cls(session=session, config=config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_apps(self, max_results: int = 25) -> list[CloudHubApp]:
        """List CloudHub 2.0 applications in the Design environment.

        Scope is hard-locked to ANYPOINT_ENV_ID (Design).
        """
        enforce_env_scope(self._config.env_id, self._config)
        limit = enforce_result_cap(max_results, self._config)

        apps = self._list_ch2_apps(limit)

        # Fall back to CloudHub 1.0 if CH2 returns nothing (some orgs use CH1)
        if not apps:
            logger.debug("CH2 returned no apps — trying CloudHub 1.0 API")
            apps = self._list_ch1_apps(limit)

        return apps

    def ping(self) -> dict:
        """Check connectivity by fetching environment metadata."""
        url = (
            f"{self._config.base_url}/accounts/api/organizations"
            f"/{self._config.bu_group_id}/environments"
        )
        resp = self._get(url)
        data = resp.json()
        envs = data.get("data", [])
        match = next((e for e in envs if e["id"] == self._config.env_id), None)
        return {
            "ok": match is not None,
            "env_name": match.get("name") if match else None,
            "env_type": match.get("type") if match else None,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _list_ch2_apps(self, limit: int) -> list[CloudHubApp]:
        """Runtime Manager API (works for both CH1 and CH2 deployments)."""
        url = f"{self._config.base_url}/armui/api/v1/applications"
        headers = {
            "X-ANYPNT-ENV-ID": self._config.env_id,
            "X-ANYPNT-ORG-ID": self._config.bu_group_id,
        }
        try:
            resp = self._get(url, headers=headers)
            data = resp.json()
            items = data.get("data", data if isinstance(data, list) else [])
            if isinstance(items, list):
                return [CloudHubApp.from_raw(item) for item in items[:limit]]
        except Exception as exc:
            logger.warning("Runtime Manager API error: %s", exc)
        return []

    def _list_ch1_apps(self, limit: int) -> list[CloudHubApp]:
        """CloudHub 1.0 API fallback."""
        url = f"{self._config.base_url}/cloudhub/api/v2/applications"
        headers = {"X-ANYPNT-ENV-ID": self._config.env_id}
        try:
            resp = self._get(url, headers=headers)
            data = resp.json()
            items = data if isinstance(data, list) else data.get("applications", [])
            return [CloudHubApp.from_raw(item) for item in items[:limit]]
        except Exception as exc:
            logger.warning("CloudHub 1.0 API error: %s", exc)
        return []

    def _get(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> requests.Response:
        """GET with one 401-retry."""
        extra_headers = headers or {}
        for attempt in range(_MAX_RETRY_401 + 1):
            resp = self._session.get(
                url,
                params=params,
                headers=extra_headers,
                timeout=self._config.http_timeout,
            )
            if resp.status_code == 401 and attempt == 0:
                if refresh_session_on_401(self._session, self._config, resp):
                    continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()  # unreachable but satisfies type checker
        return resp  # type: ignore[return-value]
