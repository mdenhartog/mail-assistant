"""Reading and labelling Gmail: the only calls the agent may use to look at mail (spec AC-2, AC-28).

This wrapper exposes these operations: find new mail, fetch one mail, make a managed label, and file a mail under
one. It has no operation that removes mail from the mailbox, and a test reads this source to keep it that way.
Attachments are never fetched (AC-23); only headers and the text part are read.

Labels are changed only for *managed* labels, by id (ADR-0060): a label that the ``ManagedSet`` does not know raises
``LabelRefused`` before Gmail is called. Errors and logs carry a code, a status and a reason, never a label name.
``ManagedLabels`` holds that logic for this module and for ``gmail_resort``.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC
from email.utils import parseaddr
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any

from googleapiclient.errors import HttpError

from app.core.managed import LabelRef, ManagedLabel, ManagedSet, Role
from category_policy import (
    ARCHIVE_LABEL_DEFAULT,
    OTHER_LABEL_DEFAULT,
    label_for,
    validate_category,
    validate_label_setting_name,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from datetime import datetime

logger = logging.getLogger(__name__)

INBOX = "INBOX"
OWN_MAIL = "SENT"
UNREAD = "UNREAD"
ME = "me"
MAX_ATTEMPTS = 5
BACKOFF_SECONDS = 1.0
HTTP_NOT_FOUND = 404
HTTP_RATE_LIMITED = 429
HTTP_SERVER_ERROR = 500
HTTP_FORBIDDEN = 403
HTTP_CONFLICT = 409
HTTP_BAD_REQUEST = 400
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


class LabelRefused(ValueError):  # noqa: N818  # a refusal, not a failure of Gmail
    """The operation is outside what the adapter may do. The message is a code, never a label name."""


class LabelNameTaken(RuntimeError):  # noqa: N818
    """Gmail already has a label with that name (HTTP 409). The message has the status and reason only."""


class LabelNameRejected(RuntimeError):  # noqa: N818
    """Gmail refused the label name (HTTP 400). The message has the status and reason only."""


class GmailLabelError(RuntimeError):
    """A label call failed at Gmail. The message has the status and the reason, never a label name or Gmail's text."""

    def __init__(self, status: int, reason: str) -> None:
        """Keep the two facts; the text of Gmail's answer can name the label, so it is dropped."""
        super().__init__(f"gmail_label_call_failed status={status} reason={reason}")
        self.status = status
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Label:
    """A Gmail label: its stable id and its name."""

    id: str
    name: str


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
    labels: frozenset[str] = field(default_factory=frozenset)
    auth_results: tuple[str, ...] = ()  # every Authentication-Results value in header order, topmost first (MC-19)


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


def retryable(error: HttpError) -> bool:
    """Whether Gmail asked us to slow down or failed on its side, so the call may be repeated."""
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


def error_reason(error: HttpError) -> str:
    """The reason code Gmail gave (such as ``labelNameExists``), or ``unknown``; never the message text."""
    try:
        return str(json.loads(error.content)["error"]["errors"][0]["reason"])
    except (ValueError, KeyError, IndexError, TypeError):
        return "unknown"


def execute(request: Any, sleep: Callable[[float], None]) -> Any:  # noqa: ANN401
    """Execute a request, retrying rate limits and server errors with exponential backoff."""
    for attempt in range(MAX_ATTEMPTS):
        try:
            return request.execute()
        except HttpError as error:
            if attempt == MAX_ATTEMPTS - 1 or not retryable(error):
                raise
            sleep(BACKOFF_SECONDS * 2**attempt)
    raise AssertionError("unreachable")  # pragma: no cover


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


_PLACEHOLDER_DESCRIPTION = "x"  # validate_category checks a description too; only the name problems matter here
_CATEGORY_ROLES = frozenset({Role.TOPIC, Role.EXTRA})
_OWN_DEFAULT = {
    Role.OTHER: OTHER_LABEL_DEFAULT,
    Role.ARCHIVE: ARCHIVE_LABEL_DEFAULT,
}  # the one reserved name a role may take


def _usable_name(role: Role, name: str) -> bool:
    """Whether ``name`` may be the name of a managed label of ``role`` (the shared category policy)."""
    if validate_label_setting_name(
        name, (), "", _OWN_DEFAULT.get(role, "")
    ):  # the length, character and Gmail system label rules
        return False
    if role in _CATEGORY_ROLES:
        return label_for(name) == name and not validate_category(name, _PLACEHOLDER_DESCRIPTION, (), ())
    return True


class ManagedLabels:
    """Label changes on one mailbox, only for managed labels and by id (ADR-0060).

    ``run`` executes a request with retries. The guard uses the label names of the latest ``list_labels`` only to
    match a managed label whose id is not stored yet; it never calls Gmail itself, so a refusal costs no call.
    """

    def __init__(self, service: Any, managed: ManagedSet, run: Callable[[Any], Any]) -> None:  # noqa: ANN401
        """Keep the service, the managed set of this run and the retrying executor."""
        self._service = service
        self._managed = managed
        self._run = run
        self._names: dict[str, str] = {}
        self._confirmed: dict[str, ManagedLabel] = {}

    def set_managed(self, managed: ManagedSet) -> None:
        """Use the managed set of a new run; ids confirmed during the old run are dropped."""
        self._managed = managed
        self._confirmed = {}

    def list_labels(self) -> list[Label]:
        """All labels of the mailbox, system labels included; refreshes the names the guard uses."""
        listing = self._run(self._service.users().labels().list(userId=ME))
        labels = [Label(str(item["id"]), str(item["name"])) for item in listing.get("labels", [])]
        self._names = {label.id: label.name for label in labels}
        return labels

    def _managed_label(self, label_id: str) -> ManagedLabel:
        found = self._confirmed.get(label_id) or self._managed.find(LabelRef(label_id, self._names.get(label_id, "")))
        if found is None:
            raise LabelRefused("label_not_managed")
        return found

    def _member(self, label: ManagedLabel) -> ManagedLabel:
        ref = LabelRef(label.label_id or "", label.name)
        found = self._confirmed.get(ref.label_id) or self._managed.find(ref)
        if found is None or found != label:
            raise LabelRefused("label_not_managed")
        return found

    def _confirm(self, label: ManagedLabel, made: Label) -> Label:
        self._confirmed[made.id] = ManagedLabel(label.name, made.id, label.role)
        self._names[made.id] = made.name
        return made

    def create(self, label: ManagedLabel) -> Label:
        """Create the managed label by its list name; an existing label of that name is adopted, mail untouched."""
        return self._create(self._member(label))

    def ensure(self, label: ManagedLabel) -> Label:
        """The label in Gmail now: the stored id when it exists, else the label of that name, else a new one.

        A label deleted by hand while its id is stored comes back as a new label; the caller stores the new id.
        """
        member = self._member(label)
        listed = self.list_labels()
        by_id = {item.id: item for item in listed}
        if member.label_id in by_id:
            return self._confirm(member, by_id[member.label_id])
        existing = next((item for item in listed if item.name.casefold() == member.name.casefold()), None)
        return self._confirm(member, existing) if existing is not None else self._create(member)

    def _create(self, label: ManagedLabel) -> Label:
        body = {"name": label.name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
        try:
            made = self._run(self._service.users().labels().create(userId=ME, body=body))
        except HttpError as error:
            status, reason = error.resp.status, error_reason(error)
            if status == HTTP_BAD_REQUEST:
                raise LabelNameRejected(f"label_name_rejected status={status} reason={reason}") from None
            if status != HTTP_CONFLICT:
                raise GmailLabelError(status, reason) from None
            logger.info("label name clash, adopting the existing label: status=%s reason=%s", status, reason)
            existing = next((x for x in self.list_labels() if x.name.casefold() == label.name.casefold()), None)
            if existing is None:
                raise GmailLabelError(status, reason) from None
            return self._confirm(label, existing)
        return self._confirm(label, Label(str(made["id"]), str(made["name"])))

    def rename(self, label_id: str, new_name: str) -> Label:
        """Patch the name of one managed label by its id; the id and the mail stay.

        When the id no longer exists in Gmail the label is created again under the new name (once); the caller
        stores the returned id.
        """
        label = self._managed_label(label_id)
        if not _usable_name(label.role, new_name):
            raise LabelRefused("new_name_not_usable")
        try:
            self._run(self._service.users().labels().patch(userId=ME, id=label_id, body={"name": new_name}))
        except HttpError as error:
            status, reason = error.resp.status, error_reason(error)
            if status == HTTP_NOT_FOUND:
                return self._create(ManagedLabel(new_name, None, label.role))
            if status == HTTP_CONFLICT:
                raise LabelNameTaken(f"label_name_taken status={status} reason={reason}") from None
            if status == HTTP_BAD_REQUEST:
                raise LabelNameRejected(f"label_name_rejected status={status} reason={reason}") from None
            raise GmailLabelError(status, reason) from None
        return self._confirm(ManagedLabel(new_name, label_id, label.role), Label(label_id, new_name))

    def add_to_mail(self, message_id: str, label_id: str, *, leave: Iterable[str] = ()) -> str:
        """Add one managed label to a mail (and take it out of ``leave``); the id used comes back.

        The archive label is never added. A label deleted by hand is created again first (once); the new id is
        the one returned.
        """
        label = self._managed_label(label_id)
        if label.role is Role.ARCHIVE:
            raise LabelRefused("label_is_archive")
        try:
            self._modify(message_id, [label_id], list(leave))
        except HttpError as error:
            if error.resp.status != HTTP_BAD_REQUEST or self._exists(label_id):
                raise
            label_id = self._create(ManagedLabel(label.name, None, label.role)).id
            self._modify(message_id, [label_id], list(leave))
        return label_id

    def remove_from_mail(self, message_id: str, label_id: str) -> None:
        """Remove one managed label from a mail; a label that no longer exists is already off the mail."""
        label = self._managed_label(label_id)
        if label.role is Role.ARCHIVE:
            raise LabelRefused("label_is_archive")
        try:
            self._modify(message_id, [], [label_id])
        except HttpError as error:
            if error.resp.status != HTTP_BAD_REQUEST or self._exists(label_id):
                raise

    def _exists(self, label_id: str) -> bool:
        return any(label.id == label_id for label in self.list_labels())

    def _modify(self, message_id: str, add: list[str], remove: list[str]) -> None:
        body: dict[str, list[str]] = {}
        if add:
            body["addLabelIds"] = add
        if remove:
            body["removeLabelIds"] = remove
        self._run(self._service.users().messages().modify(userId=ME, id=message_id, body=body))


class GmailReader:
    """Read and label mail. ``service`` is the Gmail v1 service; ``sleep`` is injectable so tests do not wait.

    Without a ``managed`` set no label is changed: every add or file is refused.
    """

    def __init__(
        self,
        service: Any,  # noqa: ANN401
        sleep: Callable[[float], None] = time.sleep,
        *,
        managed: ManagedSet | None = None,
    ) -> None:
        """Keep the service, the sleep function used between retries and the managed labels of this run."""
        self._service = service
        self._sleep = sleep
        self._labels = ManagedLabels(service, managed or ManagedSet(()), self._run)

    def _run(self, request: Any) -> Any:  # noqa: ANN401
        """Execute a request, retrying rate limits and server errors with exponential backoff."""
        return execute(request, self._sleep)

    def set_managed(self, managed: ManagedSet) -> None:
        """Use the managed labels of a new run."""
        self._labels.set_managed(managed)

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

    def list_unread_before(self, cutoff: datetime) -> list[str]:
        """Ids of unread inbox mails that arrived before ``cutoff``, in Gmail's order (newest first).

        Own sent mail is left out by the query. The cut-off must carry a timezone: Gmail takes UTC epoch seconds.
        """
        if cutoff.tzinfo is None:
            raise ValueError("the cut-off needs a timezone")
        query = f"before:{int(cutoff.astimezone(UTC).timestamp())} -in:sent"
        ids: list[str] = []
        token: str | None = None
        while True:
            request: dict[str, Any] = {"userId": ME, "labelIds": [INBOX, UNREAD], "q": query}
            if token:
                request["pageToken"] = token
            page = self._run(self._service.users().messages().list(**request))
            ids.extend(item["id"] for item in page.get("messages", []))
            token = page.get("nextPageToken")
            if not token:
                return ids

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
        # Several From headers are ambiguous (the dict above keeps one of them): fail closed, no sender at all.
        from_count = sum(1 for h in payload.get("headers", []) if h["name"].title() == "From")
        sender = parseaddr(headers.get("From", ""))[1] if from_count <= 1 else ""
        parts = _parts(payload)
        has_attachment = any(p.get("filename") or p.get("body", {}).get("attachmentId") for p in parts)
        return FetchedMail(
            message_id=raw["id"],
            thread_id=raw["threadId"],
            sender=sender,
            reply_to=parseaddr(headers["Reply-To"])[1] if "Reply-To" in headers else None,
            subject=headers.get("Subject", ""),
            text=_text_of(parts),
            has_attachment=has_attachment,
            headers=headers,
            labels=frozenset(raw.get("labelIds", [])),
            auth_results=tuple(
                h["value"] for h in payload.get("headers", []) if h["name"].title() == "Authentication-Results"
            ),
        )

    def ensure_label(self, label: ManagedLabel) -> str:
        """Id of the managed label, created when missing; an existing label of that name is adopted."""
        return self._labels.ensure(label).id

    def file(self, message_id: str, label_id: str) -> str:
        """Add one managed label and take the mail out of the inbox; nothing else about the mail changes.

        Returns the label id used: a new one when the stored label was deleted by hand.
        """
        return self._labels.add_to_mail(message_id, label_id, leave=(INBOX,))

    def add_label(self, message_id: str, label_id: str) -> str:
        """Add one more managed label (a sender rule's extra label); the inbox label and the rest stay as they are."""
        return self._labels.add_to_mail(message_id, label_id)
