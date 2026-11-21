"""U-mail-categories-39: the plan build works in slices, so the mail cycle and the heartbeat go on (ADR-0051).

A build that looked at every mail in one run kept ``deliver``, the overview and the heartbeat waiting for as long as it
took (hours for 5 000 mails), so urgent alerts came late and the liveness probe of the worker would restart the pod.
The progress is stored per mail, so a run can stop after a number of mails and the next run goes on from the cursor.
"""

from __future__ import annotations

from app.core.resort_plan import PlanState
from app.usecases.resort_build import BUILD_SLICE, BuildStatus
from tests.fakes.seeds import seed_scope_mails
from tests.resort_build_support import TRAVEL, Rig


async def test_a_run_looks_at_a_bounded_number_of_mails_and_the_next_run_goes_on_until_the_plan_is_ready() -> None:
    rig = Rig(per_run=10)
    await rig.start_plan()
    seed_scope_mails(rig.gmail, 25)
    rig.judge.answer = TRAVEL

    first = await rig.build.run_once()

    assert first.status is BuildStatus.PAUSED
    assert (rig.store.plan().state, rig.store.plan().checked, rig.judge.calls) == (PlanState.BUILDING, 10, 10)
    assert rig.telegram.texts == []  # nothing is announced before the plan is ready

    second = await rig.build.run_once()

    assert (second.status, rig.store.plan().checked, rig.judge.calls) == (BuildStatus.PAUSED, 20, 20)

    last = await rig.build.run_once()

    assert last.status is BuildStatus.READY
    assert (rig.store.plan().state, rig.store.plan().checked) == (PlanState.READY, 25)
    assert rig.judge.calls == 25  # no mail judged twice
    assert len(rig.store.items_of(rig.store.plan())) == 25
    assert len(rig.telegram.texts) == 1  # one "plan ready" notice


async def test_a_plan_with_exactly_as_many_mails_as_the_slice_is_ready_at_once_and_a_second_run_does_nothing() -> None:
    rig = Rig(per_run=10)
    await rig.start_plan()
    seed_scope_mails(rig.gmail, 10)
    rig.judge.answer = TRAVEL

    first = await rig.build.run_once()
    second = await rig.build.run_once()

    assert (first.status, rig.store.plan().checked) == (BuildStatus.READY, 10)
    assert second.status is BuildStatus.IDLE
    assert rig.judge.calls == 10  # no mail judged twice


async def test_a_build_with_fewer_mails_than_the_slice_is_ready_in_one_run() -> None:
    rig = Rig(per_run=10)
    await rig.start_plan()
    seed_scope_mails(rig.gmail, 4)
    rig.judge.answer = TRAVEL

    result = await rig.build.run_once()

    assert (result.status, rig.store.plan().checked) == (BuildStatus.READY, 4)


def test_the_slice_of_a_normal_run_is_small_enough_for_the_heartbeat() -> None:
    # About 2 to 3 seconds per judged mail: a slice has to stay far below the 180 seconds of the heartbeat probe.
    assert 1 <= BUILD_SLICE <= 25
