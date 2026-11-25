"""A Gmail v1 service double with a label and message state machine and fault hooks.

It speaks the same resource chain as ``googleapiclient`` (``users().labels().list(...).execute()``), so the real
``GmailReader`` runs on it unchanged. It models these Gmail rules:

- System labels ``INBOX``, ``SPAM``, ``TRASH``, ``UNREAD``, ``SENT`` always exist and cannot be created or renamed.
- ``SPAM``, ``TRASH`` and ``INBOX`` exclude each other: adding one removes the others.
- "Archive" is a user label named ``Archive``; a mail with no ``INBOX`` label is out of the inbox.
- Label names are unique ignoring case (409 "Label name exists or conflicts").
- A deleted mail answers 404; an unknown label id in a change answers 400; deleting a label removes it from mails.
- A label read has ``type`` (``user`` or ``system``), ``messagesTotal`` and ``threadsTotal``. Like the counters of
  Gmail, they leave out mail in spam and trash; ``messages().list`` leaves those out too unless ``includeSpamTrash``.
- ``labels().delete`` answers 404 for an unknown id and 400 for a system label. Nested names are plain names.
- ``users().settings().filters().list`` answers the filters seeded with ``add_filter`` (``{}`` without any).
- A query ``q`` is not modelled: every mail matches it.

Fault hooks fire once per call (or ``times`` calls): see ``fail_after_next_change``, ``fail_next``,
``race_on_create``, ``change_before_next_modify`` and ``inject_mail_before_next``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httplib2
from googleapiclient.errors import HttpError

SYSTEM_LABELS = ("INBOX", "SPAM", "TRASH", "UNREAD", "SENT")
_EXCLUSIVE = ("INBOX", "SPAM", "TRASH")
_HIDDEN = frozenset({"SPAM", "TRASH"})  # mail the counters and an ordinary list leave out


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
    thread: str


@dataclass
class _Faults:
    after_change: int = 0
    transient: list[int] = field(default_factory=list)
    racing_creates: set[str] = field(default_factory=set)
    refused_names: dict[str, int] = field(default_factory=dict)
    before_modify: dict[str, tuple[list[str], list[str]]] = field(default_factory=dict)
    before_call: dict[str, list[list[Any]]] = field(default_factory=dict)  # name -> [skip, hook] pairs
    failing: dict[str, list[int]] = field(default_factory=dict)  # name -> statuses for the next calls


class _Request:
    def __init__(self, action: Any) -> None:
        self._action = action

    def execute(self) -> Any:
        return self._action()


class FakeGmail:
    """The mailbox. Seed it with ``add_label``/``add_mail``; hand it to code that expects a Gmail service."""

    def __init__(self) -> None:
        self.label_table: dict[str, str] = {name: name for name in SYSTEM_LABELS}  # id -> name
        self.system_ids: set[str] = set(SYSTEM_LABELS)
        self.filter_table: list[dict[str, Any]] = []
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

    def add_system_label(self, label_id: str) -> str:
        """Seed a system label such as ``CATEGORY_PERSONAL`` (its id is its name) and return the id."""
        self.label_table[label_id] = label_id
        self.system_ids.add(label_id)
        return label_id

    def add_filter(self, add_label_ids: list[str]) -> None:
        """The user has a Gmail filter that adds these labels."""
        number = len(self.filter_table) + 1
        action = {"addLabelIds": list(add_label_ids)}
        self.filter_table.append({"id": f"filter_{number}", "criteria": {"from": "x@example.test"}, "action": action})

    def add_mail(  # noqa: PLR0913
        self,
        labels: tuple[str, ...] = ("INBOX",),
        *,
        sender: str = "sender@example.test",
        subject: str = "test-subject",
        text: str = "test-body",
        auth_results: str | None = None,
        mid: str | None = None,
        thread: str | None = None,
    ) -> str:
        """Add a mail and return its id. ``auth_results`` becomes the ``Authentication-Results`` header."""
        if mid is None:
            self._mail_seq += 1
            mid = f"m{self._mail_seq}"
        headers = {"From": sender, "Subject": subject, "Message-ID": f"<{mid}@example.test>"}
        if auth_results is not None:
            headers["Authentication-Results"] = auth_results
        self.mail_table[mid] = _Mail(mid, set(labels), headers, text, thread or f"t-{mid}")
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

    def refuse_name(self, name: str, status: int = 400) -> None:
        """Gmail refuses ``name`` for ``labels().create`` and for a rename to it (400 by default)."""
        self.faults.refused_names[name] = status

    def inject_mail_before_next(self, call: str, labels: tuple[str, ...], skip: int = 0) -> None:
        """A mail with ``labels`` arrives just before the next ``call`` (such as ``labels.delete``) runs.

        ``skip`` lets that many calls of that name pass first (``skip=1``: the second one).
        """
        self.faults.before_call.setdefault(call, []).append([skip, lambda: self.add_mail(labels=labels)])

    def fail_call(self, call: str, status: int, times: int = 1) -> None:
        """The next ``times`` calls named ``call`` (such as ``labels.get``) fail with HTTP ``status``."""
        self.faults.failing.setdefault(call, []).extend([status] * times)

    def check_name_allowed(self, name: str) -> None:
        status = self.faults.refused_names.get(name)
        if status is not None:
            raise http_error(status, "Invalid label name", "invalidArgument" if status == 400 else "forbidden")

    def change_before_next_modify(
        self, mid: str, add: list[str] | None = None, remove: list[str] | None = None
    ) -> None:
        """The user changes the mail between the caller's read and its ``modify``."""
        self.faults.before_modify[mid] = (add or [], remove or [])

    # --- the Gmail resource chain -------------------------------------------------------------------------------

    def users(self) -> FakeGmail:
        """``service.users()``."""
        return self

    def settings(self) -> _Settings:
        """``users().settings()``."""
        return _Settings(self)

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
            waiting = self.faults.before_call.pop(name, [])
            for entry in waiting:
                if entry[0] == 0:
                    entry[1]()
                else:
                    entry[0] -= 1
                    self.faults.before_call.setdefault(name, []).append(entry)
            named = self.faults.failing.get(name)
            if named or self.faults.transient:
                status = named.pop(0) if named else self.faults.transient.pop(0)
                reasons = {429: "rateLimitExceeded", 403: "forbidden"}
                raise http_error(status, "injected fault", reasons.get(status, "backendError"))
            return action()

        return _Request(run)

    def kind(self, label_id: str) -> str:
        return "system" if label_id in self.system_ids else "user"

    def check_name_free(self, name: str, except_id: str | None = None) -> None:
        taken = {n.lower() for i, n in self.label_table.items() if i != except_id}
        if name.lower() in taken:
            raise http_error(409, "Label name exists or conflicts", "labelNameExists")

    def answers_query(self, query: str, mail: _Mail) -> bool:
        """Whether ``mail`` answers the search ``query``; the base double matches all, a subclass may model it."""
        return True

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
            "threadId": mail.thread,
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
        return g.request(
            "labels.list",
            lambda: {"labels": [{"id": i, "name": n, "type": g.kind(i)} for i, n in g.label_table.items()]},
        )

    def get(self, *, id: str, **kw: Any) -> _Request:  # noqa: A002
        g = self._g

        def action() -> dict[str, Any]:
            if id not in g.label_table:
                raise http_error(404, "Requested entity was not found.", "notFound")
            counted = [m for m in g.mail_table.values() if id in m.labels and not _HIDDEN & m.labels]
            return {
                "id": id,
                "name": g.label_table[id],
                "type": g.kind(id),
                "messagesTotal": len(counted),
                "threadsTotal": len({m.thread for m in counted}),
            }

        return g.request("labels.get", action)

    def create(self, *, body: dict[str, Any], **kw: Any) -> _Request:
        g = self._g

        def action() -> dict[str, str]:
            name = str(body["name"])
            g.check_name_allowed(name)
            if name in g.faults.racing_creates:
                g.faults.racing_creates.discard(name)
                g.add_label(name)  # the overlapping run got there first
            g.check_name_free(name)
            return {"id": g.add_label(name), "name": name}

        return g.request("labels.create", action)

    def delete(self, *, id: str, **kw: Any) -> _Request:  # noqa: A002
        g = self._g

        def action() -> dict[str, Any]:
            if id not in g.label_table:
                raise http_error(404, "Requested entity was not found.", "notFound")
            if id in g.system_ids:
                raise http_error(400, "Invalid label", "invalidArgument")
            g.delete_label(id)
            return {}

        return g.request("labels.delete", action)

    def patch(self, *, id: str, body: dict[str, Any], **kw: Any) -> _Request:  # noqa: A002
        g = self._g

        def action() -> dict[str, str]:
            if id not in g.label_table or id in SYSTEM_LABELS:
                raise http_error(404 if id not in g.label_table else 400, "Invalid label", "invalidArgument")
            name = str(body["name"])
            g.check_name_allowed(name)
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
            hidden = frozenset() if kw.get("includeSpamTrash") else _HIDDEN - wanted
            found = [
                {"id": m.mid, "threadId": m.thread}
                for m in reversed(g.mail_table.values())
                if wanted <= m.labels and not hidden & m.labels and (query is None or g.answers_query(query, m))
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
            return {"id": mail.mid, "threadId": mail.thread, "labelIds": sorted(mail.labels)}

        return g.request("messages.modify", action)


class _Settings:
    def __init__(self, gmail: FakeGmail) -> None:
        self._g = gmail

    def filters(self) -> _Filters:
        return _Filters(self._g)


class _Filters:
    def __init__(self, gmail: FakeGmail) -> None:
        self._g = gmail

    def list(self, **kw: Any) -> _Request:
        g = self._g
        return g.request("settings.filters.list", lambda: {"filter": list(g.filter_table)} if g.filter_table else {})
