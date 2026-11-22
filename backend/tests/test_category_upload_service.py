"""U-label-structure-12: the comparison of a file with the stored list, without a database."""

import math
import threading
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, cast

import pytest

from app.categories_models import CategoryProblem
from app.categories_repo import RecentSaves, StoredCategory, StoredList
from app.errors import RateLimited
from app.services.category_upload import (
    CategoryUpload,
    FileRefused,
    parse_file,
    plan_of,
    policy_problems,
)
from category_policy import Kind
from category_policy.yaml_file import FILE_RULE_TEXT, ParsedList
from tests.fakes import FakeClock, FakeIds, real_minute

if TYPE_CHECKING:
    from app.categories_repo import CategoriesRepository
    from app.upload_preview_repo import UploadPreviewRepository

T0 = real_minute()
HOUR = timedelta(hours=1)

INVOICES = uuid.UUID(int=11)
OLD = uuid.UUID(int=12)
NEW = uuid.UUID(int=99)


def stored(*, labels: tuple[str, ...] = ()) -> StoredList:
    categories = (
        StoredCategory(INVOICES, "Invoices", "Bills", Kind.TOPIC, notify=False, senders=()),
        StoredCategory(OLD, "Old", "Gone soon", Kind.TOPIC, notify=False, senders=()),
    )
    return StoredList(1, categories, "", "Assistant/Archive", {}, {}, labels)


def file_of(*categories: tuple[str, str]) -> bytes:
    body = "".join(f"  - name: {name}\n    description: {description}\n" for name, description in categories)
    return f"schema: 1\ncategories:\n{body}".encode()


def test_given_equal_names_by_case_and_width_when_planned_then_they_keep_their_id_and_count_as_changed_or_same() -> (
    None
):
    parsed = parse_file(file_of(("invoices", "Bills"), ("Fresh", "d")))

    plan = plan_of(parsed, stored(), lambda: NEW)

    assert [row.id for row in plan.rows] == [INVOICES, NEW]
    assert (plan.added, plan.changed, plan.removed) == (1, 1, ["Old"])  # "invoices" differs from "Invoices" as text
    assert plan.new_ids == {NEW}


def test_given_the_same_list_when_planned_then_nothing_is_added_changed_or_removed() -> None:
    parsed = parse_file(file_of(("Invoices", "Bills"), ("Old", "Gone soon")))

    plan = plan_of(parsed, stored(), lambda: NEW)

    assert (plan.added, plan.changed, plan.removed, plan.new_ids) == (0, 0, [], frozenset())


def test_given_a_name_whose_label_is_an_older_category_when_planned_then_it_is_adopted_not_refused() -> None:
    parsed = parse_file(file_of(("Trips", "d")))

    plan = plan_of(parsed, stored(labels=("Assistant/Trips",)), lambda: NEW)

    assert [row.id for row in plan.rows] == [NEW]


def test_given_a_problem_against_the_stored_list_when_reported_then_it_names_field_and_line_but_no_value() -> None:
    found = [CategoryProblem(rule="name_label_exists", field="name", index=2, position=None, other_index=None)]

    problems = policy_problems(found)

    assert [(p.rule, p.line, p.field) for p in problems] == [("name_label_exists", 1, "categories[2].name")]
    assert problems[0].message == FILE_RULE_TEXT["name_label_exists"]


def test_given_a_hostile_file_when_parsed_then_every_problem_has_a_line_a_field_and_a_fixed_text() -> None:
    with pytest.raises(FileRefused) as refused:
        parse_file(b"schema: 1\ncategories:\n  - &a\n    name: canary-name-12\n    description: d\n    extra: x\n")

    problems = refused.value.problems
    assert {p.rule for p in problems} >= {"anchor"}
    assert all(p.line >= 1 and p.field and p.message for p in problems)
    assert "canary" not in repr(problems)


# RED-006 and RED-007 (INT-008 R1 red team): the preview limit and the parse off the event loop
class _Categories:
    async def recent_saves(self, now: datetime) -> RecentSaves:
        return RecentSaves(0, 1)

    async def read(self) -> StoredList:
        return stored()


class _Previews:
    """Keeps the previews in memory with the expiry the service gave them."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, datetime]] = []

    async def add(self, preview_id: uuid.UUID, *, session_digest: str, expires_at: datetime, **_: object) -> None:
        self.rows.append((session_digest, expires_at))

    async def recent(self, session_digest: str, now: datetime, ttl: timedelta) -> RecentSaves:
        live = sorted(at for digest, at in self.rows if digest == session_digest and at > now - HOUR + ttl)
        if not live:
            return RecentSaves(0, 1)
        wait = math.ceil((live[0] - ttl + HOUR - now).total_seconds())
        return RecentSaves(len(live), max(1, wait))


def _upload(previews: _Previews, clock: FakeClock, limit: int = 2) -> CategoryUpload:
    return CategoryUpload(
        cast("CategoriesRepository", _Categories()),
        cast("UploadPreviewRepository", previews),
        clock,
        FakeIds(),
        limit,
    )


async def test_given_the_hourly_limit_of_previews_when_one_session_uploads_again_then_it_is_refused_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previews, clock = _Previews(), FakeClock(T0)
    service = _upload(previews, clock)
    await service.preview(file_of(("A", "d")), "session-1")
    await service.preview(file_of(("B", "d")), "session-1")
    parsed: list[bytes] = []

    def refusing(data: bytes) -> ParsedList:
        parsed.append(data)
        raise AssertionError

    monkeypatch.setattr("app.services.category_upload.parse_file", refusing)

    with pytest.raises(RateLimited) as refused:
        await service.preview(file_of(("C", "d")), "session-1")

    assert 1 <= refused.value.retry_after_seconds <= 3600
    assert parsed == []
    assert len(previews.rows) == 2


async def test_given_the_limit_for_one_session_when_another_session_uploads_then_it_is_allowed() -> None:
    previews, clock = _Previews(), FakeClock(T0)
    service = _upload(previews, clock)
    await service.preview(file_of(("A", "d")), "session-1")
    await service.preview(file_of(("B", "d")), "session-1")

    await service.preview(file_of(("C", "d")), "session-2")

    assert len(previews.rows) == 3


async def test_given_the_limit_when_an_hour_has_passed_then_the_session_may_upload_again() -> None:
    previews, clock = _Previews(), FakeClock(T0)
    service = _upload(previews, clock)
    await service.preview(file_of(("A", "d")), "session-1")
    await service.preview(file_of(("B", "d")), "session-1")
    clock.advance(timedelta(hours=1, seconds=1))

    await service.preview(file_of(("C", "d")), "session-1")

    assert len(previews.rows) == 3


async def test_given_an_upload_when_it_is_parsed_then_the_parse_runs_off_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    threads: list[int] = []
    real = parse_file

    def recording(data: bytes) -> ParsedList:
        threads.append(threading.get_ident())
        return real(data)

    monkeypatch.setattr("app.services.category_upload.parse_file", recording)

    await _upload(_Previews(), FakeClock(T0), limit=5).preview(file_of(("A", "d")), "session-1")

    assert threads
    assert threading.get_ident() not in threads
