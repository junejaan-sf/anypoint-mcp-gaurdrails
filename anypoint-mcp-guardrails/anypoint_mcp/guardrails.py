"""Guardrail enforcement for Anypoint MCP.

All client calls pass through these functions before hitting the Anypoint API.
Any attempt to query outside the configured BU or environment raises
``ScopeViolationError``, which is surfaced to the AI as a clean error message.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anypoint_mcp.config import AnypointConfig

logger = logging.getLogger(__name__)


class ScopeViolationError(ValueError):
    """Raised when a request targets a BU or environment outside the allowed scope."""


def enforce_bu_scope(group_id: str, config: "AnypointConfig") -> None:
    """Raise ScopeViolationError if group_id doesn't match the configured BU."""
    if group_id != config.bu_group_id:
        raise ScopeViolationError(
            f"Scope violation: requested group ID '{group_id}' is not the configured "
            f"Integrations-NA BU ('{config.bu_group_id}'). "
            "All Exchange operations are restricted to Integrations-NA."
        )


def enforce_env_scope(env_id: str, config: "AnypointConfig") -> None:
    """Raise ScopeViolationError if env_id doesn't match the configured environment."""
    if env_id != config.env_id:
        raise ScopeViolationError(
            f"Scope violation: requested environment ID '{env_id}' is not the configured "
            f"'{config.env_name}' environment ('{config.env_id}'). "
            "CloudHub app listing is restricted to the Design environment."
        )


def enforce_result_cap(requested: int, config: "AnypointConfig") -> int:
    """Clamp the requested result count to the configured caps.

    Returns the effective limit to use in the API call.
    """
    default = config.max_results_per_request
    hard_cap = config.max_results_hard_cap

    if requested <= 0:
        effective = default
    elif requested > hard_cap:
        logger.warning(
            "Requested %d results exceeds hard cap %d — capping to %d",
            requested, hard_cap, hard_cap,
        )
        effective = hard_cap
    else:
        effective = requested

    return effective


def enforce_tool_allowed(tool_name: str, config: "AnypointConfig") -> None:
    """Raise ScopeViolationError if the tool is not in the configured allowlist.

    This check runs immediately after authentication so disallowed operations
    are rejected before any Anypoint API calls are made.
    """
    if tool_name not in config.allowed_tools:
        allowed_sorted = sorted(config.allowed_tools)
        allowed_list = ", ".join(allowed_sorted) if allowed_sorted else "(none)"
        raise ScopeViolationError(
            f"Tool '{tool_name}' is not permitted in this guardrail instance. "
            f"Allowed tools: {allowed_list}. "
            "This action is out of scope or is not allowed due to limited access. "
            "Contact your administrator to request access to additional tools."
        )


def validate_asset_id(asset_id: str) -> str:
    """Validate that an asset ID is safe for use in URL path segments.

    Anypoint asset IDs follow the pattern: lowercase alphanumeric and hyphens.
    """
    import re
    cleaned = asset_id.strip().lower()
    if not re.match(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$', cleaned) and not re.match(r'^[a-z0-9]$', cleaned):
        raise ValueError(
            f"Invalid asset ID '{asset_id}'. "
            "Asset IDs must contain only lowercase letters, digits, and hyphens."
        )
    return cleaned


def validate_version(version: str) -> str:
    """Validate that a version string follows semver (e.g. 1.0.0)."""
    import re
    v = version.strip()
    if not re.match(r'^\d+\.\d+\.\d+$', v):
        raise ValueError(
            f"Invalid version '{version}'. "
            "Versions must follow semantic versioning: MAJOR.MINOR.PATCH (e.g. 1.0.0)."
        )
    return v
