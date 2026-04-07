"""Anypoint Design Center API client.

Supports:
  - create_project()          — create a new RAML project in Design Center
  - upload_files()            — acquire branch lock and save RAML files
  - publish_to_exchange()     — publish the project branch to Exchange
  - get_owner_user_id()       — resolve the owner user ID from /accounts/api/me
"""

from __future__ import annotations

import logging
import os

import requests

from anypoint_mcp.auth import create_session, get_bearer_token, refresh_session_on_401
from anypoint_mcp.config import AnypointConfig
from anypoint_mcp.design_center.models import DesignCenterProject, DesignCenterPublishResult
from anypoint_mcp.guardrails import enforce_bu_scope, validate_asset_id, validate_version

logger = logging.getLogger(__name__)

_MAX_RETRY_401 = 1

# Files in a RAML spec folder to upload (relative paths from the spec root).
# exchange_modules are intentionally excluded — Design Center resolves
# dependencies from Exchange using the exchange.json declaration.
_RAML_SPEC_FILENAMES = {
    "exchange.json",
}


class DesignCenterClient:
    """Authenticated Anypoint Design Center API client."""

    def __init__(self, session: requests.Session, config: AnypointConfig) -> None:
        self._session = session
        self._config = config
        self._owner_user_id: str | None = None

    @classmethod
    def from_config(cls, config: AnypointConfig) -> "DesignCenterClient":
        session = create_session(config)
        return cls(session=session, config=config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_owner_user_id(self) -> str:
        """Resolve the owner user ID from /accounts/api/me (cached)."""
        if self._owner_user_id:
            return self._owner_user_id
        url = f"{self._config.base_url}/accounts/api/me"
        resp = self._get(url)
        user_id = resp.json().get("user", {}).get("id", "")
        if not user_id:
            raise ValueError("Could not resolve owner user ID from /accounts/api/me")
        self._owner_user_id = user_id
        return user_id

    def create_project(self, name: str) -> DesignCenterProject:
        """Create a new RAML project in Design Center under Integrations-NA BU.

        Design Center requires an ``x-owner-id`` header with a real user UUID
        when using client_credentials tokens (which carry no userId claim).

        Args:
            name: Project name — should match the API spec name (e.g. 'sfl-consents-sys-api-spec').
        """
        enforce_bu_scope(self._config.bu_group_id, self._config)
        owner_id = self.get_owner_user_id()

        url = f"{self._config.base_url}/designcenter/api-designer/projects"
        resp = self._post(
            url,
            json={"name": name, "type": "raml"},
            extra_headers={"x-owner-id": owner_id},
        )
        return DesignCenterProject.from_raw(resp.json())

    def get_latest_commit_id(self, project_id: str, branch: str = "master") -> str:
        """Return the latest commitId for *branch* via GET /branches.

        Called after ``upload_files()`` to capture the commit that was just
        created, so it can be included as metadata in the Exchange publish call.
        """
        url = f"{self._config.base_url}/designcenter/api-designer/projects/{project_id}/branches"
        resp = self._get(url)
        branches: list[dict] = resp.json() if isinstance(resp.json(), list) else []
        for b in branches:
            if b.get("name") == branch:
                commit_id = b.get("commitId", "")
                logger.info("Latest commitId on '%s': %s", branch, commit_id)
                return commit_id
        raise ValueError(f"Branch '{branch}' not found in project {project_id}")

    def acquire_lock(self, project_id: str, branch: str = "master") -> None:
        """Acquire the branch lock required before saving or publishing files."""
        owner_id = self.get_owner_user_id()
        url = (
            f"{self._config.base_url}/designcenter/api-designer/projects/{project_id}"
            f"/branches/{branch}/acquireLock"
        )
        resp = self._post(url, json={}, extra_headers={"x-owner-id": owner_id})
        logger.info("Branch lock acquired: %s", resp.json())

    def release_lock(self, project_id: str, branch: str = "master") -> None:
        """Release the branch lock. Always call this after save + publish."""
        owner_id = self.get_owner_user_id()
        url = (
            f"{self._config.base_url}/designcenter/api-designer/projects/{project_id}"
            f"/branches/{branch}/releaseLock"
        )
        try:
            resp = self._post(url, json={}, extra_headers={"x-owner-id": owner_id})
            logger.info("Branch lock released: %s", resp.json())
        except Exception as exc:
            logger.warning("Failed to release branch lock: %s", exc)

    def upload_files(
        self,
        project_id: str,
        spec_folder_path: str,
        branch: str = "master",
        *,
        release_lock: bool = True,
    ) -> list[dict]:
        """Acquire branch lock, discover and upload all RAML files in *spec_folder_path*.

        Files inside ``exchange_modules/`` are skipped — Design Center resolves
        dependencies declared in ``exchange.json`` from Exchange automatically.

        Args:
            project_id: Design Center project ID.
            spec_folder_path: Absolute path to the local RAML spec folder.
            branch: Branch to upload to (default: 'master').
            release_lock: If True (default), releases the branch lock after saving.
                Set to False when you intend to call publish_to_exchange() next,
                which also requires the lock to be held.

        Returns:
            List of saved file entries returned by the Design Center API.
        """
        owner_id = self.get_owner_user_id()
        extra = {"x-owner-id": owner_id}
        base = self._config.base_url

        # Acquire branch lock (required before save and publish)
        self.acquire_lock(project_id, branch)

        # Collect files (skip exchange_modules)
        file_payload: list[dict] = []
        for root, dirs, files in os.walk(spec_folder_path):
            # Prune exchange_modules subtree — DC resolves dependencies from Exchange
            dirs[:] = [d for d in dirs if d != "exchange_modules"]
            for fname in files:
                if fname.startswith("."):
                    continue
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, spec_folder_path).replace(os.sep, "/")
                with open(full_path, encoding="utf-8") as fh:
                    content = fh.read()
                file_payload.append({"path": rel_path, "content": content})
                logger.debug("Queued for upload: %s", rel_path)

        if not file_payload:
            self.release_lock(project_id, branch)
            raise ValueError(f"No files found in spec folder: {spec_folder_path}")

        save_url = (
            f"{base}/designcenter/api-designer/projects/{project_id}"
            f"/branches/{branch}/save"
        )
        try:
            save_resp = self._post(save_url, json=file_payload, extra_headers=extra)
            saved = save_resp.json()
            logger.info("Saved %d files to Design Center project %s", len(saved), project_id)
        except Exception:
            # On save failure always release the lock
            self.release_lock(project_id, branch)
            raise

        if release_lock:
            self.release_lock(project_id, branch)

        return saved

    def publish_to_exchange(
        self,
        project_id: str,
        asset_id: str,
        version: str,
        display_name: str,
        main_file: str,
        api_version: str = "v1",
        branch: str = "master",
        commit_id: str = "",
    ) -> DesignCenterPublishResult:
        """Publish a Design Center project branch to Exchange.

        The groupId is always the configured Integrations-NA BU group ID.

        Args:
            project_id: Design Center project ID.
            asset_id: Exchange asset ID (e.g. 'sfl-consents-sys-api-spec').
            version: Semantic version to publish as (e.g. '1.0.0').
            display_name: Human-readable asset name shown in Exchange.
            main_file: Root RAML filename (e.g. 'sfl-consents-sys-api-spec.raml').
            api_version: API version label (e.g. 'v1').
            branch: Design Center branch to publish from (default: 'master').
            commit_id: Optional commitId from the branch after the last save.
                       Included as ``metadata`` in the publish payload when provided,
                       linking the Exchange asset back to the exact Design Center commit.
        """
        enforce_bu_scope(self._config.bu_group_id, self._config)
        asset_id = validate_asset_id(asset_id)
        version = validate_version(version)
        owner_id = self.get_owner_user_id()

        url = (
            f"{self._config.base_url}/designcenter/api-designer/projects/{project_id}"
            f"/branches/{branch}/publish/exchange"
        )
        payload: dict = {
            "name": display_name,
            "main": main_file,
            "apiVersion": api_version,
            "version": version,
            "assetId": asset_id,
            "groupId": self._config.bu_group_id,
            "classifier": "raml",
        }
        if commit_id:
            payload["metadata"] = {
                "projectId": project_id,
                "branchId": branch,
                "commitId": commit_id,
            }
            logger.info("Publishing with metadata commitId=%s", commit_id)

        resp = self._post(url, json=payload, extra_headers={"x-owner-id": owner_id})
        return DesignCenterPublishResult.from_raw(
            resp.json(),
            project_id=project_id,
            group_id=self._config.bu_group_id,
            asset_id=asset_id,
            version=version,
        )

    # ------------------------------------------------------------------
    # Private HTTP helpers
    # ------------------------------------------------------------------

    def _dc_headers(self, extra: dict | None = None) -> dict:
        """Return headers required by Design Center API."""
        h = {
            "x-organization-id": self._config.bu_group_id,
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    def _get(self, url: str, params: dict | None = None) -> requests.Response:
        for attempt in range(_MAX_RETRY_401 + 1):
            resp = self._session.get(
                url, params=params, headers=self._dc_headers(), timeout=self._config.http_timeout
            )
            if resp.status_code == 401 and attempt == 0:
                if refresh_session_on_401(self._session, self._config, resp):
                    continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp  # type: ignore[return-value]

    def _post(
        self,
        url: str,
        json: dict | list | None = None,
        extra_headers: dict | None = None,
    ) -> requests.Response:
        for attempt in range(_MAX_RETRY_401 + 1):
            resp = self._session.post(
                url,
                json=json,
                headers=self._dc_headers(extra_headers),
                timeout=self._config.http_timeout,
            )
            if resp.status_code == 401 and attempt == 0:
                if refresh_session_on_401(self._session, self._config, resp):
                    continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp  # type: ignore[return-value]
