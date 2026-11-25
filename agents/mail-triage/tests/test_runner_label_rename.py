"""U-label-prefix-removal-06: the rename step runs right after the list sync and a failure is guarded."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.test_runner import Steps, runner

if TYPE_CHECKING:
    from pathlib import Path


class Recorder:
    def __init__(self, steps: Steps, name: str, *, fail: bool = False) -> None:
        self.steps, self.name, self.fail = steps, name, fail

    async def run_once(self) -> object:
        self.steps.calls.append(self.name)
        if self.fail:
            raise RuntimeError("boom")
        return None

    async def run(self) -> object:
        return await self.run_once()


async def test_given_a_cycle_when_run_then_the_rename_step_comes_right_after_the_list_sync(tmp_path: Path) -> None:
    steps = Steps()
    built, _ = runner(
        steps, tmp_path, list_sync=Recorder(steps, "list_sync"), label_rename=Recorder(steps, "label_rename")
    )

    await built.mail_cycle()

    assert steps.calls[:2] == ["list_sync", "label_rename"]


async def test_given_a_failing_rename_step_when_the_cycle_runs_then_the_rest_of_the_cycle_goes_on(
    tmp_path: Path,
) -> None:
    steps = Steps()
    built, _ = runner(steps, tmp_path, label_rename=Recorder(steps, "label_rename", fail=True))

    await built.mail_cycle()

    assert "label_rename" in steps.calls
    assert (tmp_path / "heartbeat").exists()
