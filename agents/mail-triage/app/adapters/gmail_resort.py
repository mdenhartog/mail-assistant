"""The narrow Gmail adapter for category labels and re-sort plans (ADR-0046 item 6, spec AC-28).

The public operations are exactly: list (labels, mail of a label), read (one mail's labels, the size of a label),
add label, remove label, create label, rename a label by id, and create or rename the archive label by id (ADR-0059).
Nothing else about a mailbox can be changed through it. A test holds the allow-list and scans this source.

Rules the adapter enforces itself, whatever the caller asks:

- Mail may only get or lose a label under ``Assistant/``; the archive label, system labels and other labels are
  refused, so the agent never files mail in the archive label (AC-25, ADR-0052).
- A rename needs a category label as its source and a category label name as its target; ``Assistant/Other`` never
  changes name. The archive label is renamed only through ``rename_archive_label``, by its id, to a usable name.
- Names under ``Assistant/`` and a usable archive label name are the only labels it creates.

The guards use label names from the latest listing; call ``list_labels`` at the start of a run.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from googleapiclient.errors import HttpError

from app.adapters.gmail_read import BACKOFF_SECONDS, MAX_ATTEMPTS, retryable
from app.core.scope import usable_archive_name
from category_policy import label_for, validate_category

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.core.scope import ArchiveLabel

LABEL_PREFIX = "Assistant/"
OTHER_LABEL = f"{LABEL_PREFIX}Other"
ME = "me"
HTTP_CONFLICT = 409
HTTP_BAD_REQUEST = 400
_PLACEHOLDER_DESCRIPTION = "x"  # validate_category checks a description too; only the name problems matter here


class LabelRefused(ValueError):  # noqa: N818  # a refusal, not a failure of Gmail
    """The operation is outside what the adapter may do."""


class LabelNameTaken(RuntimeError):  # noqa: N818
    """Gmail already has a label with that name."""


class LabelNameRejected(RuntimeError):  # noqa: N818
    """Gmail refused the label name (HTTP 400): the name cannot be used as it is. The error text is not kept."""


@dataclass(frozen=True, slots=True)
class Label:
    """A Gmail label: its stable id and its name."""

    id: str
    name: str


def is_category_label(name: str) -> bool:
    """True for ``Assistant/<name>`` when ``category-policy`` accepts ``<name>`` and the label is in its stored form."""
    if not name.startswith(LABEL_PREFIX):
        return False
    base = name[len(LABEL_PREFIX) :]
    return label_for(base) == name and not validate_category(base, _PLACEHOLDER_DESCRIPTION, (), (), ())


def _under_prefix(name: str) -> bool:
    return name.startswith(LABEL_PREFIX) and len(name) > len(LABEL_PREFIX) and ".." not in name


class GmailResort:
    """Label and list operations on one mailbox. ``service`` is the Gmail v1 service; ``sleep`` is injectable."""

    def __init__(
        self,
        service: Any,  # noqa: ANN401
        archive: ArchiveLabel,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Keep the service, the shared archive label, the sleep used between retries and the latest label names."""
        self._service = service
        self._archive = archive
        self._sleep = sleep
        self._names: dict[str, str] = {}

    def _run(self, request: Any) -> Any:  # noqa: ANN401
        for attempt in range(MAX_ATTEMPTS):
            try:
                return request.execute()
            except HttpError as error:
                if attempt == MAX_ATTEMPTS - 1 or not retryable(error):
                    raise
                self._sleep(BACKOFF_SECONDS * 2**attempt)
        raise AssertionError("unreachable")  # pragma: no cover

    def list_labels(self) -> list[Label]:
        """All labels of the mailbox, system labels included; refreshes the names the guards use."""
        listing = self._run(self._service.users().labels().list(userId=ME))
        labels = [Label(str(item["id"]), str(item["name"])) for item in listing.get("labels", [])]
        self._names = {label.id: label.name for label in labels}
        return labels

    def count_mail(self, label_id: str) -> int:
        """The number of mails that carry the label."""
        label = self._run(self._service.users().labels().get(userId=ME, id=label_id))
        return int(label.get("messagesTotal", 0))

    def list_mail(self, label_id: str) -> list[str]:
        """Ids of the mails that carry the label."""
        ids: list[str] = []
        token: str | None = None
        while True:
            request: dict[str, Any] = {"userId": ME, "labelIds": [label_id]}
            if token:
                request["pageToken"] = token
            page = self._run(self._service.users().messages().list(**request))
            ids.extend(item["id"] for item in page.get("messages", []))
            token = page.get("nextPageToken")
            if not token:
                return ids

    def read_mail(self, message_id: str) -> frozenset[str]:
        """The label ids of one mail; nothing else about it is read."""
        mail = self._run(self._service.users().messages().get(userId=ME, id=message_id, fields="id,labelIds"))
        return frozenset(mail.get("labelIds", []))

    def _name_of(self, label_id: str) -> str | None:
        if label_id not in self._names:
            self.list_labels()
        return self._names.get(label_id)

    def _require_category_label(self, label_id: str) -> None:
        name = self._name_of(label_id)
        if (
            name is None
            or not _under_prefix(name)
            or name.casefold() == self._archive.name.casefold()
            or label_id == self._archive.label_id
        ):
            raise LabelRefused("only labels under Assistant/ may be added to or removed from mail")

    def add_label(self, message_id: str, label_id: str) -> None:
        """Add one ``Assistant/`` label to a mail; nothing else about the mail changes."""
        self._require_category_label(label_id)
        body = {"addLabelIds": [label_id]}
        self._run(self._service.users().messages().modify(userId=ME, id=message_id, body=body))

    def remove_label(self, message_id: str, label_id: str) -> None:
        """Remove one ``Assistant/`` label from a mail; nothing else about the mail changes."""
        self._require_category_label(label_id)
        body = {"removeLabelIds": [label_id]}
        self._run(self._service.users().messages().modify(userId=ME, id=message_id, body=body))

    def create_label(self, name: str) -> Label:
        """Create a label under ``Assistant/``; when Gmail says it exists, return the existing one."""
        if not _under_prefix(name):
            raise LabelRefused(f"only labels under {LABEL_PREFIX} may be created")
        return self._create(name)

    def create_archive_label(self, name: str) -> Label:
        """Create the archive label under a usable name; when Gmail says it exists, return the existing one."""
        if not usable_archive_name(name):
            raise LabelRefused("the name is not a usable archive label name")
        return self._create(name)

    def _create(self, name: str) -> Label:
        body = {"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
        try:
            made = self._run(self._service.users().labels().create(userId=ME, body=body))
        except HttpError as error:
            if error.resp.status == HTTP_BAD_REQUEST:
                raise LabelNameRejected(name) from None  # the text of Gmail's answer can name the label: drop it
            if error.resp.status != HTTP_CONFLICT:
                raise
            existing = next((x for x in self.list_labels() if x.name.casefold() == name.casefold()), None)
            if existing is None:
                raise
            return existing
        label = Label(str(made["id"]), str(made["name"]))
        self._names[label.id] = label.name
        return label

    def rename_label(self, label_id: str, new_name: str) -> None:
        """Rename a category label by id; the id, the mail and the other settings stay."""
        current = self._name_of(label_id)
        if current is None or not is_category_label(current):
            raise LabelRefused("only a category label under Assistant/ can be renamed")
        if not is_category_label(new_name):
            raise LabelRefused("the new name must be a category label name under Assistant/")
        self._patch_name(label_id, new_name)

    def rename_archive_label(self, label_id: str, new_name: str) -> None:
        """Rename the archive label by its id to a usable name; the id and the mail in it stay."""
        if label_id != self._archive.label_id or self._name_of(label_id) is None:
            raise LabelRefused("only the archive label can be renamed this way")
        if not usable_archive_name(new_name):
            raise LabelRefused("the new name is not a usable archive label name")
        self._patch_name(label_id, new_name)

    def _patch_name(self, label_id: str, new_name: str) -> None:
        try:
            self._run(self._service.users().labels().patch(userId=ME, id=label_id, body={"name": new_name}))
        except HttpError as error:
            if error.resp.status == HTTP_CONFLICT:
                raise LabelNameTaken(new_name) from error
            if error.resp.status == HTTP_BAD_REQUEST:
                raise LabelNameRejected(new_name) from None
            raise
        self._names[label_id] = new_name
