"""Gmail, read only, for the plan build (INT-004, ADR-0046 item 3, spec AC-9, AC-10, AC-52).

The build lists the mail in scope (the inbox or a managed label; Gmail leaves out spam and trash) newest first, a page
at a time, and reads each mail once. This adapter has no write operation at all. The search names the managed labels
the label sync last handed over (``set_managed``); it may be wider than the scope, never narrower, because the use case
decides scope again by label id.

The cursor of a candidate is its message id: it is stored with the plan and survives a crash. Within one process the
adapter remembers where each listed mail sat (page token and index), so the next page of a run is one call. A new
process finds the cursor mail by listing from the top once. When that mail is gone, the listing starts again from the
top: mail that was judged before is not written twice (the plan item key), it only costs the calls.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Final

from googleapiclient.errors import HttpError

from app.adapters.gmail_read import BACKOFF_SECONDS, HTTP_NOT_FOUND, MAX_ATTEMPTS, GmailReader, retryable
from app.core.managed import Role
from app.usecases.resort_build import Candidate

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from app.adapters.gmail_read import FetchedMail
    from app.core.managed import ManagedSet

__all__ = ["IN_SCOPE_QUERY", "PAGE_SIZE", "WIDE_QUERY", "GmailBuild", "scope_query"]

ME: Final = "me"
PAGE_SIZE: Final = 100
HTTP_BAD_REQUEST: Final = 400
# Gmail never searches spam or trash unless asked to. Without a managed label only the inbox is in scope.
IN_SCOPE_QUERY: Final = "in:inbox -in:sent"
WIDE_QUERY: Final = "-in:sent"  # the whole mailbox: used when a label name cannot be put in a search safely
MAX_QUERY_LENGTH: Final = 1500


def scope_query(label_names: Iterable[str]) -> str:
    """The search for the inbox and these labels (Gmail also searches the labels below a label name).

    A name with a quote or a backslash, or a search that grows too long, falls back to the whole mailbox: the use case
    decides scope again by id, so a wide listing only costs calls.
    """
    names = list(label_names)
    if not names:
        return IN_SCOPE_QUERY
    if any('"' in name or "\\" in name for name in names):
        return WIDE_QUERY
    terms = " OR ".join(["in:inbox", *(f'label:"{name}"' for name in names)])
    query = f"({terms}) -in:sent"
    return query if len(query) <= MAX_QUERY_LENGTH else WIDE_QUERY


class GmailBuild:
    """The ``BuildMailbox`` port on a Gmail v1 service. ``sleep`` is injectable so tests do not wait."""

    def __init__(
        self,
        service: Any,  # noqa: ANN401
        sleep: Callable[[float], None] = time.sleep,
        page_size: int = PAGE_SIZE,
    ) -> None:
        """Keep the service, the sleep between retries, the page size and the memory of listed positions."""
        self._service = service
        self._sleep = sleep
        self._reader = GmailReader(service, sleep)
        self._page_size = page_size
        self._position: dict[str, tuple[str | None, int]] = {}  # message id -> (token of its page, index in it)
        self._managed: ManagedSet | None = None
        self._query: str | None = None  # built from the managed labels at the first listing after ``set_managed``

    def set_managed(self, managed: ManagedSet) -> None:
        """Search for the inbox and these managed labels from now on."""
        self._managed = managed
        self._query = None

    def _scope(self) -> str:
        if self._query is None:
            gmail_names = self.label_names()
            labels = (
                [label for label in self._managed.labels() if label.role is not Role.ARCHIVE] if self._managed else []
            )
            self._query = scope_query(
                gmail_names.get(label.label_id or "", label.name) if label.label_id else label.name for label in labels
            )
        return self._query

    def _run(self, request: Any) -> Any:  # noqa: ANN401
        for attempt in range(MAX_ATTEMPTS):
            try:
                return request.execute()
            except HttpError as error:
                if attempt == MAX_ATTEMPTS - 1 or not retryable(error):
                    raise
                self._sleep(BACKOFF_SECONDS * 2**attempt)
        raise AssertionError("unreachable")  # pragma: no cover

    def label_names(self) -> dict[str, str]:
        """Label id to label name."""
        listing = self._run(self._service.users().labels().list(userId=ME))
        return {str(item["id"]): str(item["name"]) for item in listing.get("labels", [])}

    def estimate_in_scope(self) -> int:
        """Gmail's own estimate of the mails the listing would return."""
        answer = self._run(self._service.users().messages().list(userId=ME, q=self._scope(), maxResults=1))
        return int(answer.get("resultSizeEstimate", 0))

    def _page(self, token: str | None) -> dict[str, Any]:
        request: dict[str, Any] = {"userId": ME, "q": self._scope(), "maxResults": self._page_size}
        if token:
            request["pageToken"] = token
        page: dict[str, Any] = self._run(self._service.users().messages().list(**request))
        for index, item in enumerate(page.get("messages", [])):
            self._position[str(item["id"])] = (token, index)
        return page

    def candidates(self, after: str | None, limit: int) -> list[Candidate]:
        """Up to ``limit`` mails in scope, newest first, strictly after the mail ``after`` (``None``: from the top)."""
        try:
            token, skip = self._start(after)
            return self._collect(token, skip, limit)
        except HttpError as error:
            if after is None or error.resp.status != HTTP_BAD_REQUEST:
                raise
            self._position.pop(after, None)  # the page token went stale: find the mail again by listing from the top
            return self._collect(*self._scan_for(after), limit)

    def _start(self, after: str | None) -> tuple[str | None, int]:
        if after is None:
            return None, 0
        if after in self._position:
            token, index = self._position[after]
            return token, index + 1
        return self._scan_for(after)

    def _scan_for(self, after: str) -> tuple[str | None, int]:
        """Where the listing continues after the mail ``after``; the top when it is no longer listed."""
        token: str | None = None
        while True:
            page = self._page(token)
            for index, item in enumerate(page.get("messages", [])):
                if item["id"] == after:
                    return token, index + 1
            token = page.get("nextPageToken")
            if not token:
                return None, 0

    def _collect(self, token: str | None, skip: int, limit: int) -> list[Candidate]:
        found: list[Candidate] = []
        while True:
            page = self._page(token)
            for item in page.get("messages", [])[skip:]:
                found.append(Candidate(str(item["id"]), str(item["id"])))
                if len(found) == limit:
                    return found
            token = page.get("nextPageToken")
            if not token:
                return found
            skip = 0

    def fetch(self, message_id: str) -> FetchedMail | None:
        """Headers, text and label ids of one mail; ``None`` when it was deleted after it was listed."""
        try:
            return self._reader.fetch(message_id)
        except HttpError as error:
            if error.resp.status == HTTP_NOT_FOUND:
                return None
            raise
