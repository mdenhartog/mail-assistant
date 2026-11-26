"""U-label-prefix-removal-09, criterion 9 at the runner: the step runs after the rename; a failure is guarded."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.settings import load_settings
from app.usecases.label_cleanup import LabelCleanup
from app.wiring import build_runner
from tests.test_runner import Steps, runner
from tests.test_settings import VALID

if TYPE_CHECKING:
    from pathlib import Path


class Recorder:
    def __init__(self, steps: Steps, name: str, *, fail: bool = False) -> None:
        self.steps, self.name, self.fail = steps, name, fail

    async def run_once(self) -> object:
        self.steps.calls.append(self.name)
        if self.fail:
            raise RuntimeError("boom with a label name: Canary")
        return None

    async def run(self) -> object:
        return await self.run_once()


async def test_given_a_cycle_when_run_then_the_cleanup_step_comes_right_after_the_rename_step(tmp_path: Path) -> None:
    steps = Steps()
    built, _ = runner(
        steps,
        tmp_path,
        list_sync=Recorder(steps, "list_sync"),
        label_rename=Recorder(steps, "label_rename"),
        label_cleanup=Recorder(steps, "label_cleanup"),
    )

    await built.mail_cycle()

    assert steps.calls[:3] == ["list_sync", "label_rename", "label_cleanup"]


async def test_given_a_failing_cleanup_step_when_the_cycle_runs_then_the_rest_of_the_cycle_goes_on(
    tmp_path: Path,
) -> None:
    steps = Steps()
    built, _ = runner(steps, tmp_path, label_cleanup=Recorder(steps, "label_cleanup", fail=True))

    await built.mail_cycle()

    assert "label_cleanup" in steps.calls
    assert "pipeline" in steps.calls
    assert (tmp_path / "heartbeat").exists()


def test_given_the_wiring_when_built_then_the_cleanup_has_the_delete_adapter_and_the_poll_interval_as_its_cycle() -> (
    None
):
    engine = create_async_engine("postgresql+asyncpg://nobody:x@127.0.0.1:1/none")  # never connected in this test
    delete: Any = object()
    built = build_runner(
        load_settings(VALID | {"POLL_INTERVAL_SECONDS": "300"}),
        sessions=async_sessionmaker(engine, expire_on_commit=False),
        client=httpx.AsyncClient(timeout=httpx.Timeout(5.0)),
        mailbox=object(),
        sender=object(),
        labels=object(),  # type: ignore[arg-type]
        label_delete=delete,
        build_mailbox=object(),  # type: ignore[arg-type]
        apply_mailbox=object(),  # type: ignore[arg-type]
        own_address="marco@example.com",
        heartbeat=None,  # type: ignore[arg-type]
        now=lambda: datetime(2026, 11, 25, tzinfo=UTC),
    )

    cleanup = vars(built)["_label_cleanup"]
    assert isinstance(cleanup, LabelCleanup)
    assert vars(cleanup)["_gmail"] is delete
    assert vars(cleanup)["_cycle"] == timedelta(seconds=300)
