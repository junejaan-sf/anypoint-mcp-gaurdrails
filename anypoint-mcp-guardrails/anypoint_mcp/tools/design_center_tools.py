"""MCP tool: anypoint_create_and_publish_design_center.

Creates a Design Center project, uploads local RAML files, and publishes
the result to Anypoint Exchange under the Integrations-NA BU.

The groupId is always hard-locked to Integrations-NA — it cannot be overridden.

Key discovery from implementation:
  - Design Center requires ``x-owner-id`` header (resolved from /accounts/api/me)
    when using client_credentials tokens, which carry no userId claim.
  - Files must be saved via ``POST /branches/{branch}/acquireLock`` first,
    then ``POST /branches/{branch}/save``.
  - exchange_modules are NOT uploaded — Design Center resolves dependencies
    declared in exchange.json from Exchange automatically.
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv

load_dotenv()

from anypoint_mcp.server import mcp  # noqa: E402
from anypoint_mcp.config import AnypointConfig  # noqa: E402
from anypoint_mcp.auth import get_bearer_token  # noqa: E402
from anypoint_mcp.design_center.client import DesignCenterClient  # noqa: E402
from anypoint_mcp.guardrails import enforce_tool_allowed  # noqa: E402

logger = logging.getLogger(__name__)


@mcp.tool()
def anypoint_create_and_publish_design_center(
    project_name: str,
    spec_folder_path: str,
    asset_id: str,
    asset_version: str,
    display_name: str,
    description: str = "",
    api_version: str = "v1",
    main_file: str = "",
) -> dict:
    """Create a Design Center project, upload RAML files, and publish to Exchange (Integrations-NA BU).

    This is the correct way to publish an editable API spec to Exchange.
    Publishing directly to Exchange (anypoint_publish_to_exchange) creates
    read-only assets with no Design Center project linkage.

    The groupId is always hard-locked to the Integrations-NA BU.

    Steps performed automatically:
      1. Create a new Design Center project (type: raml) under Integrations-NA BU
      2. Acquire the branch lock on 'master'
      3. Upload all RAML files from spec_folder_path (exchange_modules excluded)
      4. Publish the branch to Exchange

    Args:
        project_name: Design Center project name — must match the RAML spec folder
                      name (e.g. 'sfl-consents-sys-api-spec').
        spec_folder_path: Absolute local path to the RAML spec folder containing
                          the root .raml file, dataTypes/, examples/, exchange.json.
                          Do NOT include the exchange_modules/ subfolder in this path —
                          they will be automatically excluded.
        asset_id: Exchange asset ID (lowercase, hyphens only, e.g. 'sfl-consents-sys-api').
        asset_version: Semantic version to publish as (e.g. '1.0.0').
        display_name: Human-readable asset name shown in Exchange
                      (e.g. 'SFL Consents System API').
        description: Optional description shown in Exchange.
        api_version: API version label for RAML specs (e.g. 'v1'). Defaults to 'v1'.
        main_file: Root RAML filename inside the spec folder
                   (e.g. 'sfl-consents-sys-api-spec.raml'). Auto-detected if blank.
    """
    try:
        config = AnypointConfig.from_env()
        get_bearer_token(config)
        enforce_tool_allowed("anypoint_create_and_publish_design_center", config)
        client = DesignCenterClient.from_config(config)

        # Auto-detect main file if not provided
        if not main_file:
            import os
            candidates = [
                f for f in os.listdir(spec_folder_path)
                if f.endswith(".raml") and not f.startswith(".")
            ]
            if len(candidates) == 1:
                main_file = candidates[0]
            else:
                raml_named = [f for f in candidates if asset_id.replace("-spec", "") in f or project_name in f]
                main_file = raml_named[0] if raml_named else (candidates[0] if candidates else f"{project_name}.raml")
            logger.info("Auto-detected main file: %s", main_file)

        # Step 1: Create Design Center project
        logger.info("Creating Design Center project: %s", project_name)
        project = client.create_project(project_name)
        logger.info("Project created: %s (id=%s)", project.name, project.project_id)

        # Steps 2 & 3: Acquire lock + upload files.
        # release_lock=False keeps the lock held — Design Center's publish API
        # also requires the caller to hold the branch lock.
        logger.info("Uploading files from: %s", spec_folder_path)
        saved_files = client.upload_files(
            project_id=project.project_id,
            spec_folder_path=spec_folder_path,
            release_lock=False,
        )
        logger.info("Uploaded %d files", len(saved_files))

        # Fetch the commitId created by the save above so it can be embedded as
        # metadata in the Exchange asset, linking it back to the exact DC commit.
        commit_id = client.get_latest_commit_id(project.project_id)
        logger.info("Captured commitId for publish metadata: %s", commit_id)

        # Step 4: Publish to Exchange (lock must still be held), then release.
        logger.info("Publishing to Exchange as %s v%s", asset_id, asset_version)
        try:
            result = client.publish_to_exchange(
                project_id=project.project_id,
                asset_id=asset_id,
                version=asset_version,
                display_name=display_name,
                main_file=main_file,
                api_version=api_version,
                commit_id=commit_id,
            )
        finally:
            client.release_lock(project.project_id)

        return {
            "ok": True,
            "message": (
                f"Successfully published '{display_name}' v{asset_version} to Exchange "
                f"via Design Center. The asset is now editable."
            ),
            "project": project.to_dict(),
            "published": result.to_dict(),
            "files_uploaded": len(saved_files),
        }

    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc)}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("anypoint_create_and_publish_design_center failed")
        return {"ok": False, "error": str(exc)}
