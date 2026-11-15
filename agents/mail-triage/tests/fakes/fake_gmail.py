"""A Gmail v1 service double with a label and message state machine and fault hooks.

It speaks the same resource chain as ``googleapiclient`` (``users().labels().list(...).execute()``), so the real
``GmailReader`` runs on it unchanged. It models these Gmail rules:

- System labels ``INBOX``, ``SPAM``, ``TRASH``, ``UNREAD``, ``SENT`` always exist and cannot be created or renamed.
- ``SPAM``, ``TRASH`` and ``INBOX`` exclude each other: adding one removes the others.
- "Archive" is a user label named ``Archive``; a mail with no ``INBOX`` label is out of the inbox.
- Label names are unique ignoring case (409 "Label name exists or conflicts").
- A deleted mail answers 404; an unknown label id in a change answers 400; deleting a label removes it from mails.

Fault hooks fire once per call (or ``times`` calls): see ``fail_after_next_change``, ``fail_next``,
``race_on_create`` and ``change_before_next_modify``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httplib2
from googleapiclient.errors import HttpError

SYSTEM_LABELS = ("INBOX", "SPAM", "TRASH", "UNREAD", "SENT")
_EXCLUSIVE = ("INBOX", "SPAM", "TRASH")
ASSISTANT_PREFIX = "Assistant/"


def http_error(status: int, message: str, reason: str = "") -> HttpError:
    """An ``HttpError`` shaped like the one Gmail returns."""
    body = {"error": {"code": status, "message": message, "errors": [{"message": message, "reason": reason}]}}
    return HttpError(httplib2.Response({"status": status}), json.dumps(body).encode())


@dataclass
class _Mail:
    mid: str
    labels: set[str]
    headers: dict[str, str]
    text: str


@dataclass
class _Faults:
    after_change: int = 0
    transient: list[int] = field(default_factory=list)
    racing_creates: set[str] = field(default_factory=set)
    before_modify: dict[str, tuple[list[str], list[str]]] = field(default_factory=dict)


class _Request:
    def __init__(self, action: Any) -> None:
        self._action = action

    def execute(self) -> Any:
        return self._action()


class FakeGmail:
    """The mailbox. Seed it with ``add_label``/``add_mail``; hand it to code that expects a Gmail service."""

    def __init__(self) -> None:
        self.label_table: dict[str, str] = {name: name for name in SYSTEM_LABELS}  # id -> name
        self.mail_table: dict[str, _Mail] = {}
        self.faults = _Faults()
        self._label_seq = 0
        self._mail_seq = 0
        self.calls: list[str] = []

    # --- seeding and inspection ---------------------------------------------------------------------------------

    def add_label(self, name: str) -> str:
        """Create a user label directly (as the user would) and return its id."""
        self.check_name_free(name)
        self._label_seq += 1
        label_id = f"Label_{self._label_seq}"
        self.label_table[label_id] = name
        return label_id

    def add_mail(  # noqa: PLR0913
        self,
        labels: tuple[str, ...] = ("INBOX",),
        *,
        sender: str = "sender@example.test",
        subject: str = "test-subject",
        text: str = "test-body",
        auth_results: str | None = None,
        mid: str | None = None,
    ) -> str:
        """Add a mail and return its id. ``auth_results`` becomes the ``Authentication-Results`` header."""
        if mid is None:
            self._mail_seq += 1
            mid = f"m{self._mail_seq}"
        headers = {"From": sender, "Subject": subject, "Message-ID": f"<{mid}@example.test>"}
        if auth_results is not None:
            headers["Authentication-Results"] = auth_results
        self.mail_table[mid] = _Mail(mid, set(labels), headers, text)
        return mid

    def delete_mail(self, mid: str) -> None:
        """The user deletes the mail for good."""
        del self.mail_table[mid]

    def delete_label(self, label_id: str) -> None:
        """The user deletes a label; every mail loses it."""
        del self.label_table[label_id]
        for mail in self.mail_table.values():
            mail.labels.discard(label_id)

    def label_names(self) -> list[str]:
        """All label names, system labels included."""
        return list(self.label_table.values())

    def label_id(self, name: str) -> str:
        """Id of the label ``name`` (exact match)."""
        return next(i for i, n in self.label_table.items() if n == name)

    def assistant_label_count(self, mid: str) -> int:
        """How many ``Assistant/`` labels the mail carries (AC-52)."""
        return sum(1 for i in self.mail_table[mid].labels if self.label_table[i].startswith(ASSISTANT_PREFIX))

    # --- fault hooks --------------------------------------------------------------------------------------------

    def fail_after_next_change(self) -> None:
        """The next ``modify`` applies its change, then raises ``ConnectionResetError`` (before the caller DB write)."""
        self.faults.after_change += 1

    def fail_next(self, status: int, times: int = 1) -> None:
        """The next ``times`` calls (any resource) fail with HTTP ``status`` and change nothing."""
        self.faults.transient.extend([status] * times)

    def race_on_create(self, name: str) -> None:
        """The next ``labels().create`` of ``name`` finds it made by an overlapping run: 409, one label stays."""
        self.faults.racing_creates.add(name)

    def change_before_next_modify(
        self, mid: str, add: list[str] | None = None, remove: list[str] | None = None
    ) -> None:
        """The user changes the mail between the caller's read and its ``modify``."""
        self.faults.before_modify[mid] = (add or [], remove or [])

    # --- the Gmail resource chain -------------------------------------------------------------------------------

    def users(self) -> FakeGmail:
        """``service.users()``."""
        return self

    def getProfile(self, **kw: Any) -> _Request:  # noqa: N802
        """``users().getProfile``: a fixed history position."""
        return self.request("getProfile", lambda: {"emailAddress": "me@example.test", "historyId": "100"})

    def labels(self) -> _Labels:
        """``users().labels()``."""
        return _Labels(self)

    def messages(self) -> _Messages:
        """``users().messages()``."""
        return _Messages(self)

    # --- internals ----------------------------------------------------------------------------------------------

    def request(self, name: str, action: Any) -> _Request:
        def run() -> Any:
            self.calls.append(name)
            if self.faults.transient:
                status = self.faults.transient.pop(0)
                raise http_error(status, "injected fault", "rateLimitExceeded" if status == 429 else "backendError")
            return action()

        return _Request(run)

    def check_name_free(self, name: str, except_id: str | None = None) -> None:
        taken = {n.lower() for i, n in self.label_table.items() if i != except_id}
        if name.lower() in taken:
            raise http_error(409, "Label name exists or conflicts", "labelNameExists")

    def matches_query(self, query: str, mail: _Mail) -> bool:
        """The plan build's search, ``in:inbox OR label:assistant`` (spam and trash are never searched).

        Any other query is not modelled and matches everything, as the double always did.
        """
        terms = [term.strip() for term in query.split(" OR ")]
        if not set(terms) <= {"in:inbox", "label:assistant"}:
            return True
        if {"SPAM", "TRASH"} & mail.labels:
            return False
        names = {self.label_table[i] for i in mail.labels}
        tests = {
            "in:inbox": "INBOX" in mail.labels,
            "label:assistant": any(n.startswith(ASSISTANT_PREFIX) for n in names),
        }
        return any(tests[term] for term in terms)

    def get_mail(self, mid: str) -> _Mail:
        try:
            return self.mail_table[mid]
        except KeyError:
            raise http_error(404, "Requested entity was not found.", "notFound") from None

    def apply_change(self, mail: _Mail, add: list[str], remove: list[str]) -> None:
        for label_id in (*add, *remove):
            if label_id not in self.label_table:
                raise http_error(400, f"Invalid label: {label_id}", "invalidArgument")
        mail.labels -= set(remove)
        for label_id in add:
            if label_id in _EXCLUSIVE:
                mail.labels -= set(_EXCLUSIVE)
            mail.labels.add(label_id)

    def payload_of(self, mail: _Mail) -> dict[str, Any]:
        return {
            "id": mail.mid,
            "threadId": f"t-{mail.mid}",
            "labelIds": sorted(mail.labels),
            "payload": {
                "mimeType": "text/plain",
                "headers": [{"name": k, "value": v} for k, v in mail.headers.items()],
                "body": {"data": _b64(mail.text)},
            },
        }


def _b64(text: str) -> str:
    import base64  # noqa: PLC0415

    return base64.urlsafe_b64encode(text.encode()).decode()


class _Labels:
    def __init__(self, gmail: FakeGmail) -> None:
        self._g = gmail

    def list(self, **kw: Any) -> _Request:
        g = self._g
        return g.request("labels.list", lambda: {"labels": [{"id": i, "name": n} for i, n in g.label_table.items()]})

    def get(self, *, id: str, **kw: Any) -> _Request:  # noqa: A002
        g = self._g

        def action() -> dict[str, Any]:
            if id not in g.label_table:
                raise http_error(404, "Requested entity was not found.", "notFound")
            total = sum(1 for m in g.mail_table.values() if id in m.labels)
            return {"id": id, "name": g.label_table[id], "messagesTotal": total}

        return g.request("labels.get", action)

    def create(self, *, body: dict[str, Any], **kw: Any) -> _Request:
        g = self._g

        def action() -> dict[str, str]:
            name = str(body["name"])
            if name in g.faults.racing_creates:
                g.faults.racing_creates.discard(name)
                g.add_label(name)  # the overlapping run got there first
            g.check_name_free(name)
            return {"id": g.add_label(name), "name": name}

        return g.request("labels.create", action)

    def patch(self, *, id: str, body: dict[str, Any], **kw: Any) -> _Request:  # noqa: A002
        g = self._g

        def action() -> dict[str, str]:
            if id not in g.label_table or id in SYSTEM_LABELS:
                raise http_error(404 if id not in g.label_table else 400, "Invalid label", "invalidArgument")
            name = str(body["name"])
            g.check_name_free(name, except_id=id)
            g.label_table[id] = name
            return {"id": id, "name": name}

        return g.request("labels.patch", action)


class _Messages:
    def __init__(self, gmail: FakeGmail) -> None:
        self._g = gmail

    def list(self, **kw: Any) -> _Request:
        g = self._g

        def action() -> dict[str, Any]:
            wanted = set(kw.get("labelIds", []))
            query = kw.get("q")
            found = [
                {"id": m.mid, "threadId": f"t-{m.mid}"}
                for m in reversed(g.mail_table.values())
                if wanted <= m.labels and (query is None or g.matches_query(str(query), m))
            ]
            size, start = kw.get("maxResults"), int(kw.get("pageToken", 0))
            page = found[start : start + size] if size else found
            answer: dict[str, Any] = {"messages": page} if page else {}
            if size and start + size < len(found):
                answer["nextPageToken"] = str(start + size)  # an offset: stable while the mailbox does not change
            if query is not None:
                answer["resultSizeEstimate"] = len(found)
            return answer

        return g.request("messages.list", action)

    def get(self, *, id: str, **kw: Any) -> _Request:  # noqa: A002
        g = self._g
        return g.request("messages.get", lambda: g.payload_of(g.get_mail(id)))

    def modify(self, *, id: str, body: dict[str, Any], **kw: Any) -> _Request:  # noqa: A002
        g = self._g

        def action() -> dict[str, Any]:
            mail = g.get_mail(id)
            if id in g.faults.before_modify:
                add, remove = g.faults.before_modify.pop(id)
                g.apply_change(mail, add, remove)
            g.apply_change(mail, list(body.get("addLabelIds", [])), list(body.get("removeLabelIds", [])))
            if g.faults.after_change:
                g.faults.after_change -= 1
                raise ConnectionResetError("injected: the change is made, the answer is lost")
            return {"id": mail.mid, "threadId": f"t-{mail.mid}", "labelIds": sorted(mail.labels)}

        return g.request("messages.modify", action)
