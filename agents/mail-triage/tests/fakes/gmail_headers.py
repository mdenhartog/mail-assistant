"""A Gmail v1 double that returns raw message headers exactly as stored (U-label-structure-01, AC-15).

Headers are an ordered tuple of ``(name, value)`` pairs, so duplicates, folded lines, forged, missing and
non-Gmail ``Authentication-Results``, several or no ``From`` and an attached ``message/rfc822`` all survive a round
trip untouched. A fold keeps its ``CRLF`` plus the leading white space in the value. Fixtures are plain text files in
``header_fixtures/`` (anonymised: reserved domains, documentation IPs, ``test-`` message ids).

The fake keeps only message ids in its call record; it never keeps header values for logging.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httplib2
from googleapiclient.errors import HttpError

FIXTURE_DIR = Path(__file__).parent / "header_fixtures"
ATTACHED_MARKER = "=== attached message/rfc822 ==="
FOLD = "\r\n"

type RawHeaders = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class HeaderFixture:
    """One stored header set, plus the headers of an attached ``message/rfc822`` when the fixture has one."""

    headers: RawHeaders
    attached: RawHeaders | None = None


def parse_header_block(text: str) -> RawHeaders:
    """Split a header block into ``(name, value)`` pairs, keeping order, duplicates and folds."""
    pairs: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line:
            continue
        if line[0] in " \t":
            if not pairs:
                raise ValueError("a folded line cannot start a header block")
            name, value = pairs[-1]
            pairs[-1] = (name, f"{value}{FOLD}{line}")
            continue
        name, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"not a header line: {name[:20]!r}")
        pairs.append((name, value.removeprefix(" ")))
    return tuple(pairs)


def fixture_names() -> list[str]:
    """The names of all stored fixtures."""
    return sorted(path.stem for path in FIXTURE_DIR.glob("*.txt"))


def load_fixture(name: str) -> HeaderFixture:
    """Read ``header_fixtures/<name>.txt``; an optional attached message follows the marker line."""
    text = (FIXTURE_DIR / f"{name}.txt").read_text(encoding="utf-8")
    outer, marker, inner = text.partition(ATTACHED_MARKER)
    return HeaderFixture(
        headers=parse_header_block(outer),
        attached=parse_header_block(inner) if marker else None,
    )


def _http_404(message_id: str) -> HttpError:
    body = {"error": {"code": 404, "message": "Requested entity was not found.", "errors": []}}
    error = HttpError(httplib2.Response({"status": 404}), json.dumps(body).encode())
    error.args = (f"message {message_id} not found",)
    return error


def _as_gmail_headers(headers: RawHeaders) -> list[dict[str, str]]:
    return [{"name": name, "value": value} for name, value in headers]


class _Request:
    def __init__(self, action: Any) -> None:
        self._action = action

    def execute(self) -> dict[str, Any]:
        return self._action()  # type: ignore[no-any-return]


class _Messages:
    def __init__(self, owner: FakeHeaderGmail) -> None:
        self._owner = owner

    def get(self, *, userId: str, id: str, format: str = "full", **_: object) -> _Request:  # noqa: A002, N803
        """``users().messages().get(...)``; ``userId`` and ``format`` are accepted and ignored."""
        del userId, format
        return _Request(lambda: self._owner.message_payload(id))


class _Users:
    def __init__(self, owner: FakeHeaderGmail) -> None:
        self._owner = owner

    def messages(self) -> _Messages:
        return _Messages(self._owner)


class FakeHeaderGmail:
    """Seed with ``add_message``; hand it to code that expects a Gmail service and reads message headers."""

    def __init__(self) -> None:
        self._messages: dict[str, tuple[RawHeaders, RawHeaders | None]] = {}
        self.fetched: list[str] = []

    def add_message(self, message_id: str, headers: RawHeaders, *, attached: RawHeaders | None = None) -> None:
        """Store a message; ``attached`` becomes a ``message/rfc822`` part with its own headers."""
        self._messages[message_id] = (headers, attached)

    def users(self) -> _Users:
        """The first link of the ``googleapiclient`` resource chain."""
        return _Users(self)

    def message_payload(self, message_id: str) -> dict[str, Any]:
        """The Gmail ``Message`` resource for one id; raises a 404 ``HttpError`` for an unknown id."""
        self.fetched.append(message_id)
        if message_id not in self._messages:
            raise _http_404(message_id)
        headers, attached = self._messages[message_id]
        payload: dict[str, Any] = {"headers": _as_gmail_headers(headers)}
        if attached is not None:
            payload["parts"] = [{"mimeType": "message/rfc822", "headers": _as_gmail_headers(attached)}]
        return {"id": message_id, "payload": payload}
