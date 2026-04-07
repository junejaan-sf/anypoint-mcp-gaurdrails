"""MCP tool: anypoint_health_check.

Verifies connectivity to both CloudHub and Exchange APIs using the
configured Integrations-NA credentials.
"""

from __future__ import annotations

import logging
import time

from dotenv import load_dotenv

load_dotenv()

from anypoint_mcp.server import mcp  # noqa: E402
from anypoint_mcp.config import AnypointConfig  # noqa: E402
from anypoint_mcp.auth import get_bearer_token  # noqa: E402
from anypoint_mcp.cloudhub.client import CloudHubClient  # noqa: E402
from anypoint_mcp.exchange.client import ExchangeClient  # noqa: E402
from anypoint_mcp.guardrails import enforce_tool_allowed  # noqa: E402

logger = logging.getLogger(__name__)


@mcp.tool()
def anypoint_health_check() -> dict:
    """Check connectivity to Anypoint Platform (CloudHub + Exchange).

    Verifies that the Connected App credentials are valid and that both
    CloudHub (Design environment) and Exchange (Integrations-NA BU) are reachable.

    Returns a JSON summary with ok/error status for each service.
    """
    result: dict = {"ok": True}

    # Auth check
    t0 = time.monotonic()
    try:
        config = AnypointConfig.from_env()
        token = get_bearer_token(config)
        enforce_tool_allowed("anypoint_health_check", config)
        result["auth"] = {
            "ok": True,
            "client_id": config.client_id[:8] + "...",
            "latency_ms": round((time.monotonic() - t0) * 1000),
        }
    except Exception as exc:
        result["ok"] = False
        result["auth"] = {"ok": False, "error": str(exc)}
        return result

    # CloudHub check
    t1 = time.monotonic()
    try:
        ch_client = CloudHubClient.from_config(config)
        ch_ping = ch_client.ping()
        result["cloudhub"] = {
            **ch_ping,
            "env_id": config.env_id,
            "latency_ms": round((time.monotonic() - t1) * 1000),
        }
        if not ch_ping.get("ok"):
            result["ok"] = False
    except Exception as exc:
        result["ok"] = False
        result["cloudhub"] = {"ok": False, "error": str(exc)}

    # Exchange check
    t2 = time.monotonic()
    try:
        ex_client = ExchangeClient.from_config(config)
        ex_ping = ex_client.ping()
        result["exchange"] = {
            **ex_ping,
            "bu_group_id": config.bu_group_id,
            "latency_ms": round((time.monotonic() - t2) * 1000),
        }
        if not ex_ping.get("ok"):
            result["ok"] = False
    except Exception as exc:
        result["ok"] = False
        result["exchange"] = {"ok": False, "error": str(exc)}

    result["scope"] = {
        "bu": "Integrations-NA",
        "bu_group_id": config.bu_group_id,
        "cloudhub_env": config.env_name,
        "cloudhub_env_id": config.env_id,
    }

    return result
