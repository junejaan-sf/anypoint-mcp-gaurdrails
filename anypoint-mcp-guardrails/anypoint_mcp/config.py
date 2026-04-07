"""Configuration for Anypoint MCP Guardrails.

All configuration is loaded from environment variables via ``from_env()``.
Scope identifiers (BU group ID, environment ID) are validated at load time
so the server fails fast if misconfigured rather than at tool invocation time.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_REQUIRED_ENV_VARS = (
    "ANYPOINT_CLIENT_ID",
    "ANYPOINT_CLIENT_SECRET",
    "ANYPOINT_ORG_ID",
    "ANYPOINT_BU_GROUP_ID",
    "ANYPOINT_ENV_ID",
)

ALL_KNOWN_TOOLS: frozenset[str] = frozenset({
    "anypoint_health_check",
    "anypoint_list_apps",
    "anypoint_search_exchange",
    "anypoint_publish_to_exchange",
    "anypoint_create_and_publish_design_center",
})


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


def _validate_url(url: str, label: str) -> str:
    url = url.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ConfigError(f"{label} must start with http:// or https://, got: {url!r}")
    if not parsed.netloc:
        raise ConfigError(f"{label} has no host: {url!r}")
    return url


@dataclass(slots=True)
class AnypointConfig:
    # Anypoint Platform base URL
    base_url: str

    # Connected App credentials
    client_id: str
    client_secret: str

    # Scope locks
    org_id: str
    bu_group_id: str
    env_id: str
    env_name: str

    # Result caps
    max_results_per_request: int
    max_results_hard_cap: int
    http_timeout: int

    # Logging
    log_level: str

    # Tool allowlist — empty frozenset means all tools are permitted
    allowed_tools: frozenset

    @classmethod
    def from_env(cls) -> "AnypointConfig":
        missing = [v for v in _REQUIRED_ENV_VARS if not os.environ.get(v)]
        if missing:
            raise ConfigError(
                f"Missing required environment variable(s): {', '.join(missing)}. "
                "Copy .env.example to .env and fill in your Anypoint Connected App credentials."
            )

        base_url = _validate_url(
            os.environ.get("ANYPOINT_BASE_URL", "https://anypoint.mulesoft.com"),
            "ANYPOINT_BASE_URL",
        )

        raw_allowed = os.environ.get("ALLOWED_TOOLS", "").strip()
        if raw_allowed:
            allowed_tools: frozenset[str] = frozenset(
                t.strip() for t in raw_allowed.split(",") if t.strip()
            )
        else:
            allowed_tools = ALL_KNOWN_TOOLS

        config = cls(
            base_url=base_url,
            client_id=os.environ["ANYPOINT_CLIENT_ID"],
            client_secret=os.environ["ANYPOINT_CLIENT_SECRET"],
            org_id=os.environ["ANYPOINT_ORG_ID"],
            bu_group_id=os.environ["ANYPOINT_BU_GROUP_ID"],
            env_id=os.environ["ANYPOINT_ENV_ID"],
            env_name=os.environ.get("ANYPOINT_ENV_NAME", ""),
            max_results_per_request=int(os.environ.get("MAX_RESULTS_PER_REQUEST", "25")),
            max_results_hard_cap=int(os.environ.get("MAX_RESULTS_HARD_CAP", "100")),
            http_timeout=int(os.environ.get("HTTP_TIMEOUT", "30")),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            allowed_tools=allowed_tools,
        )

        logger.debug(
            "AnypointConfig loaded: base_url=%s org=%s bu_group=%s env=%s(%s)",
            config.base_url,
            config.org_id,
            config.bu_group_id,
            config.env_id,
            config.env_name,
        )
        return config
