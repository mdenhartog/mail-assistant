"""Keep mail text, tokens and the API key out of logs and error reports (spec AC-14, AC-24; threat model T-09).

Three layers: known secret values are replaced wherever they appear; key and token shapes are replaced even when the
value is not known (a Telegram bot token sits inside request URLs); and fields that carry mail text are replaced by
name. Error reports also lose every local variable, because a frame's variables can hold a whole mail.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

REDACTED = "[redacted]"
SENSITIVE_FIELDS = frozenset({"mail_body", "body", "text", "snippet", "payload", "draft_body"})
_SHAPES = (
    (re.compile(r"(?<=bot)\d+:[A-Za-z0-9_-]+"), "<redacted>"),  # Telegram bot token inside an API URL
    (re.compile(r"sk-ant-[A-Za-z0-9_-]+"), REDACTED),  # Anthropic key
    (re.compile(r"(?i)(?<=bearer )[A-Za-z0-9._~+/=-]+"), REDACTED),  # bearer tokens
)


class Redactor:
    """Replace secrets in text. ``secrets`` are the exact values this process holds (key, bot token, ...)."""

    def __init__(self, secrets: Iterable[str]) -> None:
        """Remember the known secret values, longest first so a long value is not half-replaced."""
        self._secrets = sorted({s for s in secrets if s}, key=len, reverse=True)

    def scrub(self, text: str) -> str:
        """Return ``text`` without known secrets and without anything shaped like a key or token."""
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        for pattern, replacement in _SHAPES:
            text = pattern.sub(replacement, text)
        return text


class RedactionFilter(logging.Filter):
    """Scrub every log record before any handler sees it."""

    def __init__(self, redactor: Redactor) -> None:
        """Keep the redactor used on every record."""
        super().__init__()
        self._redactor = redactor

    def filter(self, record: logging.LogRecord) -> bool:
        """Scrub the message and replace the fields that carry mail text."""
        record.msg = self._redactor.scrub(record.getMessage())
        record.args = None
        for name in SENSITIVE_FIELDS:
            if hasattr(record, name):
                setattr(record, name, REDACTED)
        return True


def _clean(node: Any, redactor: Redactor) -> Any:  # noqa: ANN401
    if isinstance(node, dict):
        mapping = cast("dict[str, Any]", node)
        return {
            key: REDACTED if key in SENSITIVE_FIELDS else _clean(value, redactor)
            for key, value in mapping.items()
            if key != "vars"  # local variables of a stack frame are dropped entirely
        }
    if isinstance(node, list):
        return [_clean(item, redactor) for item in cast("list[Any]", node)]
    if isinstance(node, str):
        return redactor.scrub(node)
    return node


def sentry_before_send(redactor: Redactor) -> Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None]:
    """A ``before_send`` hook for the error tracker that scrubs the whole event and drops local variables."""

    def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
        return _clean(event, redactor)  # type: ignore[no-any-return]

    return before_send
