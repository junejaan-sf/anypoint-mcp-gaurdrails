"""FastMCP server for Anypoint MCP Guardrails.

Exposes scoped tools for Anypoint Platform (Integrations-NA BU):
- ``anypoint_list_apps``                        — List CloudHub apps in Design environment (read-only)
- ``anypoint_search_exchange``                  — Search Exchange assets in Integrations-NA BU (read-only)
- ``anypoint_publish_to_exchange``              — Publish an API spec directly to Exchange (write, BU-locked)
- ``anypoint_create_and_publish_design_center`` — Create Design Center project + publish to Exchange (editable asset)
- ``anypoint_health_check``                     — Connectivity and credential validation

Run with:
    python -m anypoint_mcp.server
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

mcp = FastMCP(name="anypoint-mcp-guardrails")

_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# Import tool modules to register tools via @mcp.tool() decorators.
# Each module imports ``mcp`` from this module at import time.
from anypoint_mcp.tools import cloudhub_tools  # noqa: F401, E402
from anypoint_mcp.tools import design_center_tools  # noqa: F401, E402
from anypoint_mcp.tools import exchange_tools  # noqa: F401, E402
from anypoint_mcp.tools import health_tools  # noqa: F401, E402


def main() -> None:
    """Entry point for the MCP server (stdio transport)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
