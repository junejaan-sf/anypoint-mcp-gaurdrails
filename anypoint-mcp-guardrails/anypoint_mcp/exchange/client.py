"""Anypoint Exchange API v2 client.

Supports:
  - search_assets()  — read-only, scoped to Integrations-NA BU group ID
  - publish_asset()  — write, groupId always hard-locked to BU group ID
"""

from __future__ import annotations

import logging
import os

import requests

from anypoint_mcp.auth import create_session, refresh_session_on_401
from anypoint_mcp.config import AnypointConfig
from anypoint_mcp.exchange.models import ApiAsset, PublishResult
from anypoint_mcp.guardrails import (
    enforce_bu_scope,
    enforce_result_cap,
    validate_asset_id,
    validate_version,
)

logger = logging.getLogger(__name__)

_MAX_RETRY_401 = 1

_READABLE_TYPES = "rest-api,raml-fragment,soap-api,http-api,oas-spec"


class ExchangeClient:
    """Authenticated Anypoint Exchange API v2 client."""

    def __init__(self, session: requests.Session, config: AnypointConfig) -> None:
        self._session = session
        self._config = config

    @classmethod
    def from_config(cls, config: AnypointConfig) -> "ExchangeClient":
        session = create_session(config)
        return cls(session=session, config=config)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def search_assets(
        self,
        search: str = "",
        asset_types: str = _READABLE_TYPES,
        max_results: int = 25,
    ) -> list[ApiAsset]:
        """Search Exchange assets scoped to Integrations-NA BU.

        Args:
            search: Free-text search term. Empty string returns all assets.
            asset_types: Comma-separated asset type filter.
            max_results: Number of results to return (capped by config).
        """
        enforce_bu_scope(self._config.bu_group_id, self._config)
        limit = enforce_result_cap(max_results, self._config)

        # Build params list — types must be repeated (not comma-joined) because the
        # Exchange API does not support comma-encoded multi-value in a single param.
        params_list: list[tuple[str, str]] = [
            ("organizationId", self._config.bu_group_id),
            ("limit", str(limit)),
            ("offset", "0"),
        ]
        for t in asset_types.split(","):
            t = t.strip()
            if t:
                params_list.append(("types", t))
        if search:
            params_list.append(("search", search))

        url = f"{self._config.base_url}/exchange/api/v2/assets"
        resp = self._get(url, params=params_list)
        data = resp.json()

        items = data if isinstance(data, list) else data.get("assets", data.get("data", []))
        return [ApiAsset.from_raw(item) for item in items[:limit]]

    def get_asset(self, asset_id: str, version: str | None = None) -> ApiAsset:
        """Fetch a single Exchange asset by ID (and optionally version)."""
        enforce_bu_scope(self._config.bu_group_id, self._config)
        asset_id = validate_asset_id(asset_id)

        if version:
            url = (
                f"{self._config.base_url}/exchange/api/v2/assets"
                f"/{self._config.bu_group_id}/{asset_id}/{version}"
            )
        else:
            url = (
                f"{self._config.base_url}/exchange/api/v2/assets"
                f"/{self._config.bu_group_id}/{asset_id}"
            )

        resp = self._get(url)
        return ApiAsset.from_raw(resp.json())

    def ping(self) -> dict:
        """Check Exchange connectivity by fetching the first asset."""
        try:
            assets = self.search_assets(max_results=1)
            return {"ok": True, "assets_visible": len(assets)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Write operations (scoped to Integrations-NA BU)
    # ------------------------------------------------------------------

    def publish_asset(
        self,
        asset_id: str,
        version: str,
        name: str,
        spec_file_path: str,
        description: str = "",
        api_version: str = "v1",
        main_file: str = "",
        keywords: str = "",
    ) -> PublishResult:
        """Publish an API spec to Exchange under Integrations-NA BU.

        The groupId is always the configured BU group ID — callers cannot override it.

        Args:
            asset_id: Exchange asset ID (e.g. 'sfl-consent-sys-api').
            version: Semantic version (e.g. '1.0.0').
            name: Human-readable asset name shown in Exchange.
            spec_file_path: Absolute path to a .zip file containing the RAML or OAS spec.
            description: Optional description shown in Exchange.
            api_version: API version label (e.g. 'v1'). Used for RAML apiVersion field.
            main_file: Main file name inside the zip (e.g. 'api.raml'). Auto-detected if blank.
            keywords: Comma-separated keywords/tags for Exchange search.
        """
        # Scope and input validation
        enforce_bu_scope(self._config.bu_group_id, self._config)
        asset_id = validate_asset_id(asset_id)
        version = validate_version(version)

        if not os.path.isfile(spec_file_path):
            raise FileNotFoundError(f"Spec file not found: {spec_file_path}")

        # Determine classifier from file extension
        lower_path = spec_file_path.lower()
        if lower_path.endswith(".raml"):
            classifier, packaging = "raml", "raml"
        elif lower_path.endswith((".yaml", ".yml")):
            classifier, packaging = "oas", "yaml"
        elif lower_path.endswith(".json"):
            classifier, packaging = "oas", "json"
        elif "raml" in lower_path:
            classifier, packaging = "raml", "zip"
        else:
            classifier, packaging = "oas", "zip"

        url = (
            f"{self._config.base_url}/exchange/api/v2/organizations"
            f"/{self._config.org_id}/assets"
            f"/{self._config.bu_group_id}/{asset_id}/{version}"
        )

        multipart: dict = {}
        if name:
            multipart["name"] = (None, name)
        if description:
            multipart["description"] = (None, description)
        if keywords:
            multipart["keywords"] = (None, keywords)
        if api_version:
            multipart["properties.apiVersion"] = (None, api_version)
        if main_file:
            multipart["properties.mainFile"] = (None, main_file)

        file_key = f"files.{classifier}.{packaging}"
        with open(spec_file_path, "rb") as fh:
            multipart[file_key] = (os.path.basename(spec_file_path), fh, "application/octet-stream")
            resp = self._post_multipart(url, multipart)

        result_data = resp.json() if resp.content else {}
        logger.info(
            "Published asset %s/%s@%s to Exchange (HTTP %d)",
            self._config.bu_group_id, asset_id, version, resp.status_code,
        )
        return PublishResult.from_raw(result_data, self._config.bu_group_id, asset_id, version)

    # ------------------------------------------------------------------
    # Private HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, params: dict | list | None = None) -> requests.Response:
        for attempt in range(_MAX_RETRY_401 + 1):
            resp = self._session.get(url, params=params, timeout=self._config.http_timeout)
            if resp.status_code == 401 and attempt == 0:
                if refresh_session_on_401(self._session, self._config, resp):
                    continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp  # type: ignore[return-value]

    def _post_multipart(self, url: str, files: dict) -> requests.Response:
        for attempt in range(_MAX_RETRY_401 + 1):
            resp = self._session.post(
                url,
                files=files,
                headers={"x-sync-publication": "true"},
                timeout=self._config.http_timeout,
            )
            if resp.status_code == 401 and attempt == 0:
                if refresh_session_on_401(self._session, self._config, resp):
                    continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp  # type: ignore[return-value]
