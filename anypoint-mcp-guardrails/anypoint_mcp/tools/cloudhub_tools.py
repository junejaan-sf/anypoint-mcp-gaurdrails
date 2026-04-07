"""MCP tool: anypoint_list_apps.

Lists CloudHub applications in the configured Design environment
(Integrations-NA BU). Read-only — no mutations.
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv

load_dotenv()

from anypoint_mcp.server import mcp  # noqa: E402
from anypoint_mcp.config import AnypointConfig  # noqa: E402
from anypoint_mcp.auth import get_bearer_token  # noqa: E402
from anypoint_mcp.cloudhub.client import CloudHubClient  # noqa: E402
from anypoint_mcp.guardrails import enforce_tool_allowed  # noqa: E402

logger = logging.getLogger(__name__)


@mcp.tool()
def anypoint_list_apps(max_results: int = 25) -> dict:
    """List CloudHub applications in the Integrations-NA Design environment.

    Returns the name, status, Mule runtime version, replica count, domain, and
    last-modified timestamp for each deployed application.

    This tool is read-only and scoped to the Design environment only.

    Args:
        max_results: Maximum number of apps to return (default 25, hard cap 100).
    """
    try:
        config = AnypointConfig.from_env()
        get_bearer_token(config)
        enforce_tool_allowed("anypoint_list_apps", config)
        client = CloudHubClient.from_config(config)
        apps = client.list_apps(max_results=max_results)

        if not apps:
            return {
                "ok": True,
                "count": 0,
                "environment": config.env_name,
                "apps": [],
                "message": "No applications found in the Design environment.",
            }

        return {
            "ok": True,
            "count": len(apps),
            "environment": config.env_name,
            "env_id": config.env_id,
            "bu": "Integrations-NA",
            "apps": [app.to_dict() for app in apps],
        }

    except Exception as exc:
        logger.exception("anypoint_list_apps failed")
        return {"ok": False, "error": str(exc)}
