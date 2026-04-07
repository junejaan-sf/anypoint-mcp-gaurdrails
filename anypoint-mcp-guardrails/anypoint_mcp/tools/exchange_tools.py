"""MCP tools: anypoint_search_exchange and anypoint_publish_to_exchange.

anypoint_search_exchange  — read-only, scoped to Integrations-NA BU.
anypoint_publish_to_exchange — write, groupId always locked to Integrations-NA BU.
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv

load_dotenv()

from anypoint_mcp.server import mcp  # noqa: E402
from anypoint_mcp.config import AnypointConfig  # noqa: E402
from anypoint_mcp.auth import get_bearer_token  # noqa: E402
from anypoint_mcp.exchange.client import ExchangeClient  # noqa: E402
from anypoint_mcp.guardrails import enforce_tool_allowed  # noqa: E402

logger = logging.getLogger(__name__)


@mcp.tool()
def anypoint_search_exchange(
    search: str = "",
    asset_types: str = "rest-api,raml-fragment,soap-api,http-api",
    max_results: int = 25,
) -> dict:
    """Search Anypoint Exchange for API specs and assets in the Integrations-NA BU.

    This tool is read-only. Results are scoped to the Integrations-NA business group.

    Args:
        search: Free-text search term (e.g. 'consent', 'patient', 'crm').
                Leave empty to list all assets.
        asset_types: Comma-separated asset types to filter by.
                     Options: rest-api, raml-fragment, soap-api, http-api, oas-spec.
        max_results: Maximum number of assets to return (default 25, hard cap 100).
    """
    try:
        config = AnypointConfig.from_env()
        get_bearer_token(config)
        enforce_tool_allowed("anypoint_search_exchange", config)
        client = ExchangeClient.from_config(config)
        assets = client.search_assets(
            search=search,
            asset_types=asset_types,
            max_results=max_results,
        )

        if not assets:
            return {
                "ok": True,
                "count": 0,
                "bu": "Integrations-NA",
                "search": search or "(all)",
                "assets": [],
                "message": "No assets found matching your search.",
            }

        return {
            "ok": True,
            "count": len(assets),
            "bu": "Integrations-NA",
            "bu_group_id": config.bu_group_id,
            "search": search or "(all)",
            "asset_types": asset_types,
            "assets": [a.to_dict() for a in assets],
        }

    except Exception as exc:
        logger.exception("anypoint_search_exchange failed")
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def anypoint_publish_to_exchange(
    asset_id: str,
    version: str,
    name: str,
    spec_file_path: str,
    description: str = "",
    api_version: str = "v1",
    main_file: str = "",
    keywords: str = "",
) -> dict:
    """Publish an API specification to Anypoint Exchange under Integrations-NA BU.

    The groupId is always hard-locked to the Integrations-NA BU — it cannot be
    overridden. The caller provides only the asset-specific fields.

    Supported spec formats:
    - RAML: provide a .raml file or a .zip containing the RAML spec
    - OAS/Swagger: provide a .yaml, .yml, .json, or .zip containing the spec

    Args:
        asset_id: Exchange asset ID (lowercase, hyphens allowed, e.g. 'sfl-consent-sys-api').
        version: Semantic version string (e.g. '1.0.0').
        name: Human-readable asset name shown in Exchange (e.g. 'SFL Consent System API').
        spec_file_path: Absolute local path to the spec file (.raml, .yaml, .json, or .zip).
        description: Optional description shown in Exchange.
        api_version: API version label for RAML specs (e.g. 'v1'). Defaults to 'v1'.
        main_file: Main file name inside a zip archive (e.g. 'api.raml').
                   Leave empty for single-file specs or for auto-detection.
        keywords: Comma-separated keywords for Exchange search (e.g. 'crm,patient,consent').
    """
    try:
        config = AnypointConfig.from_env()
        get_bearer_token(config)
        enforce_tool_allowed("anypoint_publish_to_exchange", config)
        client = ExchangeClient.from_config(config)

        result = client.publish_asset(
            asset_id=asset_id,
            version=version,
            name=name,
            spec_file_path=spec_file_path,
            description=description,
            api_version=api_version,
            main_file=main_file,
            keywords=keywords,
        )

        return {
            "ok": True,
            "message": f"Successfully published '{name}' v{version} to Integrations-NA Exchange.",
            **result.to_dict(),
        }

    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc)}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("anypoint_publish_to_exchange failed")
        return {"ok": False, "error": str(exc)}
