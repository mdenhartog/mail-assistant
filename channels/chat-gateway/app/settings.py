"""Runtime settings from the environment. A channel is only switched on when fully and safely configured."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast, get_args

if TYPE_CHECKING:
    from collections.abc import Mapping

AgentBackend = Literal["http", "agentcore"]
BIND_HOST = "0.0.0.0"  # noqa: S104  # nosec B104
_SECRET_TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,256}$")  # the characters Telegram allows in a webhook secret
_MIN_SECRET = 16


class SettingsError(ValueError):
    """The configuration is unsafe or incomplete; the gateway must not start."""


@dataclass(frozen=True, slots=True)
class TelegramSettings:
    """Telegram Bot API: the webhook secret and the chats that may talk to the agent."""

    bot_token: str
    webhook_secret: str
    allowed_chat_ids: frozenset[int]


@dataclass(frozen=True, slots=True)
class WhatsAppSettings:
    """WhatsApp Cloud API: the app secret signs every webhook; only allow-listed numbers reach the agent."""

    app_secret: str
    verify_token: str
    access_token: str
    phone_number_id: str
    allowed_numbers: frozenset[str]
    api_version: str


@dataclass(frozen=True, slots=True)
class Settings:
    """Which agent to call and which channels are on."""

    agent_backend: AgentBackend
    agent_url: str | None
    agent_token: str | None
    agent_runtime_arn: str | None
    region: str | None
    reply_timeout: float
    telegram: TelegramSettings | None
    whatsapp: WhatsAppSettings | None
    port: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Read and validate; raise ``SettingsError`` on anything unsafe, and when no channel is enabled."""
        source = os.environ if env is None else env
        backend = source.get("AGENT_BACKEND", "http")
        if backend not in get_args(AgentBackend):
            raise SettingsError(f"AGENT_BACKEND must be one of {', '.join(get_args(AgentBackend))}")
        url = source.get("AGENT_URL") or None
        arn = source.get("AGENT_RUNTIME_ARN") or None
        if backend == "http" and url is None:
            raise SettingsError("AGENT_URL is required when AGENT_BACKEND=http")
        if backend == "agentcore" and arn is None:
            raise SettingsError("AGENT_RUNTIME_ARN is required when AGENT_BACKEND=agentcore")
        telegram, whatsapp = _telegram(source), _whatsapp(source)
        if telegram is None and whatsapp is None:
            raise SettingsError("Enable at least one channel: set TELEGRAM_BOT_TOKEN or WHATSAPP_ACCESS_TOKEN")
        return cls(
            agent_backend=cast("AgentBackend", backend),
            agent_url=url.rstrip("/") if url else None,
            agent_token=source.get("AGENT_TOKEN") or None,
            agent_runtime_arn=arn,
            region=source.get("AWS_REGION") or source.get("AWS_DEFAULT_REGION") or None,
            reply_timeout=float(source.get("REPLY_TIMEOUT_SECONDS", "60")),
            telegram=telegram,
            whatsapp=whatsapp,
            port=int(source.get("PORT", "8000")),
        )


def _require(source: Mapping[str, str], keys: tuple[str, ...], channel: str) -> list[str]:
    values = [source.get(key, "") for key in keys]
    missing = [key for key, value in zip(keys, values, strict=True) if not value]
    if missing:
        raise SettingsError(f"{channel} is partly configured; missing: {', '.join(missing)}")
    return values


def _telegram(source: Mapping[str, str]) -> TelegramSettings | None:
    if not source.get("TELEGRAM_BOT_TOKEN"):
        return None
    token, secret, chats = _require(
        source, ("TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRET", "TELEGRAM_ALLOWED_CHAT_IDS"), "Telegram"
    )
    if not _SECRET_TOKEN.match(secret):
        raise SettingsError("TELEGRAM_WEBHOOK_SECRET must be 16-256 characters of A-Z a-z 0-9 _ -")
    try:
        ids = frozenset(int(part) for part in chats.split(",") if part.strip())
    except ValueError as error:
        raise SettingsError("TELEGRAM_ALLOWED_CHAT_IDS must be a comma-separated list of numeric chat ids") from error
    return TelegramSettings(bot_token=token, webhook_secret=secret, allowed_chat_ids=ids)


def _whatsapp(source: Mapping[str, str]) -> WhatsAppSettings | None:
    if not source.get("WHATSAPP_ACCESS_TOKEN"):
        return None
    keys = (
        "WHATSAPP_APP_SECRET",
        "WHATSAPP_VERIFY_TOKEN",
        "WHATSAPP_ACCESS_TOKEN",
        "WHATSAPP_PHONE_NUMBER_ID",
        "WHATSAPP_ALLOWED_NUMBERS",
    )
    app_secret, verify_token, access_token, phone_number_id, numbers = _require(source, keys, "WhatsApp")
    if len(verify_token) < _MIN_SECRET:
        raise SettingsError("WHATSAPP_VERIFY_TOKEN must be at least 16 characters")
    allowed = frozenset(part.strip().lstrip("+") for part in numbers.split(",") if part.strip())
    return WhatsAppSettings(
        app_secret=app_secret,
        verify_token=verify_token,
        access_token=access_token,
        phone_number_id=phone_number_id,
        allowed_numbers=allowed,
        api_version=source.get("WHATSAPP_API_VERSION", "v23.0"),
    )
