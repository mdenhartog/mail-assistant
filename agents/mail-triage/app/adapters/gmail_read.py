"""Reading and labelling Gmail: the only calls the agent may use to look at mail (spec AC-2, AC-28).

This wrapper exposes four operations: find new mail, fetch one mail, make a category label, and file a mail under
one. It has no operation that removes mail from the mailbox, and a test scans this source to keep it that way.
Attachments are never fetched (AC-23); only headers and the text part are read.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from email.utils import parseaddr
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any

from googleapiclient.errors import HttpError

if TYPE_CHECKING:
    from collections.abc import Callable

LABEL_PREFIX = "Assistant/"
INBOX = "INBOX"
OWN_MAIL = "SENT"
ME = "me"
MAX_ATTEMPTS = 5
BACKOFF_SECONDS = 1.0
HTTP_NOT_FOUND = 404
HTTP_RATE_LIMITED = 429
HTTP_SERVER_ERROR = 500
HTTP_FORBIDDEN = 403
RATE_REASONS = frozenset({"rateLimitExceeded", "userRateLimitExceeded"})
KEPT_HEADERS = (
    "From",
    "Reply-To",
    "Subject",
    "Message-ID",
    "Auto-Submitted",
    "List-Id",
    "Precedence",
    "Authentication-Results",
)
_PART = "mimeType,filename,headers(name,value),body(data,attachmentId,size)"
FIELDS = (
    "id,threadId,labelIds,payload(mimeType,headers(name,value),body(data,attachmentId,size),"
    f"parts({_PART},parts({_PART},parts({_PART}))))"
)


class HistoryExpiredError(RuntimeError):
    """Gmail no longer has the stored history position; the caller must start again from now."""


@dataclass(frozen=True, slots=True)
class FetchedMail:
    """What the agent reads of one mail. No attachment content, only whether one exists."""

    message_id: str
    thread_id: str
    sender: str
    reply_to: str | None
    subject: str
    text: str
    has_attachment: bool
    headers: dict[str, str]


class _TextOnly(HTMLParser):
    """Collect visible text from HTML, skipping script and style."""

    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._skip += tag in {"script", "style"}

    def handle_endtag(self, tag: str) -> None:
        self._skip -= tag in {"script", "style"} and self._skip > 0

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The payload and all nested parts, flattened."""
    found = [payload]
    for part in payload.get("parts", []):
        found.extend(_parts(part))
    return found


def _text_of(parts: list[dict[str, Any]]) -> str:
    for wanted in ("text/plain", "text/html"):
        for part in parts:
            data = part.get("body", {}).get("data")
            if part.get("mimeType") == wanted and data and not part.get("filename"):
                raw = _decode(data)
                if wanted == "text/plain":
                    return raw.strip()
                extractor = _TextOnly()
                extractor.feed(raw)
                return " ".join(extractor.parts)
    return ""


def _retryable(error: HttpError) -> bool:
    status = error.resp.status
    if status == HTTP_RATE_LIMITED or status >= HTTP_SERVER_ERROR:
        return True
    if status != HTTP_FORBIDDEN:
        return False
    try:
        reasons = {item.get("reason") for item in json.loads(error.content)["error"]["errors"]}
    except (ValueError, KeyError, TypeError):
        return False
    return bool(reasons & RATE_REASONS)


def _inbox_ids(page: dict[str, Any]) -> list[str]:
    """Ids of mails added to the inbox on one history page; the agent's own sent mail is left out (AC-29)."""
    found: list[str] = []
    for entry in page.get("history", []):
        for added in entry.get("messagesAdded", []):
            message = added["message"]
            labels = message.get("labelIds", [])
            if INBOX in labels and OWN_MAIL not in labels:
                found.append(message["id"])
    return found


class GmailReader:
    """Read and label mail. ``service`` is the Gmail v1 service; ``sleep`` is injectable so tests do not wait."""

    def __init__(self, service: Any, sleep: Callable[[float], None] = time.sleep) -> None:  # noqa: ANN401
        """Keep the service and the sleep function used between retries."""
        self._service = service
        self._sleep = sleep

    def _run(self, request: Any) -> Any:  # noqa: ANN401
        """Execute a request, retrying rate limits and server errors with exponential backoff."""
        for attempt in range(MAX_ATTEMPTS):
            try:
                return request.execute()
            except HttpError as error:
                if attempt == MAX_ATTEMPTS - 1 or not _retryable(error):
                    raise
                self._sleep(BACKOFF_SECONDS * 2**attempt)
        raise AssertionError("unreachable")  # pragma: no cover

    def list_new(self, history_id: str | None) -> tuple[list[str], str]:
        """Ids of inbox mails added since ``history_id`` (oldest first) and the new position.

        Without a stored position nothing old is processed: the agent starts from now.
        """
        if history_id is None:
            profile = self._run(self._service.users().getProfile(userId=ME))
            return [], str(profile["historyId"])
        ids: list[str] = []
        latest = history_id
        token: str | None = None
        while True:
            page = self._history_page(history_id, token)
            latest = str(page.get("historyId", latest))
            ids.extend(i for i in _inbox_ids(page) if i not in ids)
            token = page.get("nextPageToken")
            if not token:
                return ids, latest

    def _history_page(self, history_id: str, token: str | None) -> dict[str, Any]:
        query: dict[str, Any] = {
            "userId": ME,
            "startHistoryId": history_id,
            "historyTypes": ["messageAdded"],
            "labelId": INBOX,
        }
        if token:
            query["pageToken"] = token
        try:
            return self._run(self._service.users().history().list(**query))  # type: ignore[no-any-return]
        except HttpError as error:
            if error.resp.status == HTTP_NOT_FOUND:
                raise HistoryExpiredError from error
            raise

    def fetch(self, message_id: str) -> FetchedMail:
        """Headers and text of one mail. Attachment content is never requested."""
        raw = self._run(
            self._service.users().messages().get(userId=ME, id=message_id, format="full", fields=FIELDS),
        )
        payload = raw["payload"]
        headers = {
            h["name"].title(): h["value"] for h in payload.get("headers", []) if h["name"].title() in KEPT_HEADERS
        }
        parts = _parts(payload)
        has_attachment = any(p.get("filename") or p.get("body", {}).get("attachmentId") for p in parts)
        return FetchedMail(
            message_id=raw["id"],
            thread_id=raw["threadId"],
            sender=parseaddr(headers.get("From", ""))[1],
            reply_to=parseaddr(headers["Reply-To"])[1] if "Reply-To" in headers else None,
            subject=headers.get("Subject", ""),
            text=_text_of(parts),
            has_attachment=has_attachment,
            headers=headers,
        )

    def ensure_label(self, name: str) -> str:
        """Id of the label ``name``, created when missing. Only names under ``Assistant/`` are allowed."""
        if not name.startswith(LABEL_PREFIX) or len(name) == len(LABEL_PREFIX) or ".." in name:
            raise ValueError(f"label names must start with {LABEL_PREFIX}")
        listing = self._run(self._service.users().labels().list(userId=ME))
        for label in listing.get("labels", []):
            if label["name"] == name:
                return str(label["id"])
        body = {"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
        return str(self._run(self._service.users().labels().create(userId=ME, body=body))["id"])

    def file(self, message_id: str, label_id: str) -> None:
        """Add one category label and take the mail out of the inbox; nothing else about the mail changes."""
        body = {"addLabelIds": [label_id], "removeLabelIds": [INBOX]}
        self._run(self._service.users().messages().modify(userId=ME, id=message_id, body=body))
