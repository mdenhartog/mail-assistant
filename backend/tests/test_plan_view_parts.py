"""U-mail-categories-32: the parts of the plan view built from the open plan and from the last ended plan."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.plan_repo import EndedPlan, OpenPlan
from app.routers.plan import last_plan_view, progress_view

ENDED_AT = datetime(2026, 11, 15, 14, 20, tzinfo=UTC)


def test_given_no_open_plan_when_the_progress_is_built_then_every_number_is_zero_and_the_estimate_is_unknown() -> None:
    progress = progress_view(None)

    assert (progress.checked, progress.cap, progress.unclear, progress.not_looked_at) == (0, 0, 0, 0)
    assert progress.estimate is None


def test_given_an_open_plan_when_the_progress_is_built_then_the_numbers_of_the_plan_are_shown() -> None:
    plan = OpenPlan(
        id=uuid.uuid4(),
        state="building",
        apply_after=None,
        checked=340,
        cap=2000,
        unclear=3,
        estimate=1900,
        not_looked_at=7,
        list_version=1,
        request_id=None,
        threshold=None,
    )

    progress = progress_view(plan)

    assert (progress.checked, progress.cap, progress.unclear, progress.estimate, progress.not_looked_at) == (
        340,
        2000,
        3,
        1900,
        7,
    )


def test_given_no_ended_plan_when_the_last_plan_is_built_then_there_is_none() -> None:
    assert last_plan_view(None) is None


def test_given_an_ended_plan_when_the_last_plan_is_built_then_state_end_time_and_moved_count_are_shown() -> None:
    ended = EndedPlan(id=uuid.uuid4(), state="applied", ended_at=ENDED_AT, moved=12)

    last = last_plan_view(ended)

    assert last is not None
    assert (last.id, last.state, last.ended_at, last.moved_count) == (ended.id, "applied", ENDED_AT, 12)
