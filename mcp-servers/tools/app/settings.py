"""Runtime settings, read once from the environment (fail closed)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast, get_args

if TYPE_CHECKING:
    from collections.abc import Mapping

AuthMode = Literal["token", "platform", "off"]
_DEFAULT_PORT = 8000  # AgentCore Runtime serves MCP on 8000 at /mcp
_MIN_TOKEN_LENGTH = 32
BIND_HOST = "0.0.0.0"  # noqa: S104  # nosec B104


class SettingsError(ValueError):
    """The configuration is unsafe or incomplete; the server must not start."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Who may call the server and where it listens.

    ``token``: a static bearer token (self-hosted: Docker, Kubernetes).
    ``platform``: AgentCore Runtime authenticates the caller (SigV4 or JWT) before the request reaches the container.
    ``off``: local development only; refused when ``APP_ENVIRONMENT`` is ``production``.
    """

    auth_mode: AuthMode
    auth_token: str
    port: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Read and validate the settings; raise ``SettingsError`` on anything unsafe."""
        source = os.environ if env is None else env
        mode = source.get("MCP_AUTH_MODE", "token")
        if mode not in get_args(AuthMode):
            raise SettingsError(f"MCP_AUTH_MODE must be one of {', '.join(get_args(AuthMode))}")
        token = source.get("MCP_AUTH_TOKEN", "")
        if mode == "token" and len(token) < _MIN_TOKEN_LENGTH:
            raise SettingsError("MCP_AUTH_TOKEN must be set to at least 32 characters in token mode")
        if mode == "off" and source.get("APP_ENVIRONMENT", "production") == "production":
            raise SettingsError("MCP_AUTH_MODE=off is only allowed when APP_ENVIRONMENT is not production")
        return cls(auth_mode=cast("AuthMode", mode), auth_token=token, port=int(source.get("PORT", str(_DEFAULT_PORT))))
