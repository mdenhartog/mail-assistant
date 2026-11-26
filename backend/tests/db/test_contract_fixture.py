"""U-web-settings-21, criterion 7: the shared contract cases run through the web repository (AC-26)."""

import json
import re
from datetime import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.exc import DBAPIError

from app.db import Database
from app.settings_repo import DEFAULT_CLEANUP, LabelCleanup, SettingsRepository
from schedule_policy.policy import TimePolicy

CASES_FILE = Path(__file__).resolve().parents[3] / "packages" / "schedule-policy" / "contract" / "settings_cases.json"
ALL_CASES: list[dict[str, Any]] = json.loads(CASES_FILE.read_text("utf-8"))["cases"]
# Rules the migration's CHECK constraints also enforce; the others need code (known zone) or cannot be stored.
DATABASE_RULES = {"quiet_window_empty", "quiet_window_length", "overview_in_quiet_hours", "remind_in_quiet_hours"}
MALFORMED_TIME_RULES = {"time_not_whole_minute", "time_has_zone"}
ACTOR = "0123456789abcdef0123456789abcdef"
# Malformed times cannot be stored as minutes, so those cases never reach this test; filtering here, not skipping in
# the test, keeps a skip from ever hiding a failure of this file (CR-12).
CASES: list[dict[str, Any]] = [case for case in ALL_CASES if not set(case["rules"]) & MALFORMED_TIME_RULES]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
async def test_given_a_contract_case_when_written_through_the_repository_then_the_outcome_matches_the_package(
    case: dict[str, Any], web_database: Database
) -> None:
    rules = set(case["rules"])
    raw = case["policy"]
    policy = TimePolicy(
        raw["zone"],
        time.fromisoformat(raw["quiet_start"]),
        time.fromisoformat(raw["quiet_end"]),
        time.fromisoformat(raw["overview_at"]),
        time.fromisoformat(raw["remind_at"]),
    )
    zone_shape_ok = re.fullmatch(r"[A-Za-z_]+(/[A-Za-z0-9_+-]+){0,2}", raw["zone"]) is not None
    # A well-formed but unknown zone is beyond SQL (ADR-0025): the database lets it through, validate refuses it.
    expected_accepted = not (rules & DATABASE_RULES) and zone_shape_ok
    repo = SettingsRepository(web_database)

    if expected_accepted:
        stored = await repo.write(policy, DEFAULT_CLEANUP, 0, ACTOR)
        assert (stored.policy, stored.version) == (policy, 1)
    else:
        with pytest.raises(DBAPIError):
            await repo.write(policy, DEFAULT_CLEANUP, 0, ACTOR)
        assert (await repo.read()).version == 0


def test_given_the_contract_cases_when_selected_then_the_unstorable_ones_are_left_out_before_the_run_not_skipped() -> (
    None
):
    assert not [case["id"] for case in CASES if set(case["rules"]) & MALFORMED_TIME_RULES]
    assert CASES  # the filter must not empty the run


# The label cleanup numbers (AC 33, 34): the database CHECKs are the last line behind the code checks.
CLEANUP_POLICY = TimePolicy("Europe/Amsterdam", time(22, 0), time(7, 0), time(8, 0), time(12, 0))
IN_RANGE_CLEANUPS = [
    LabelCleanup(5, 1, 7),
    LabelCleanup(720, 30, 90),
    LabelCleanup(60, 14, 45),
]
OUT_OF_RANGE_CLEANUPS = [
    LabelCleanup(4, 7, 30),
    LabelCleanup(721, 7, 30),
    LabelCleanup(60, 0, 30),
    LabelCleanup(60, 31, 30),
    LabelCleanup(60, 7, 6),
    LabelCleanup(60, 7, 91),
]


@pytest.mark.parametrize("cleanup", IN_RANGE_CLEANUPS, ids=repr)
async def test_given_cleanup_numbers_in_range_when_written_then_they_are_read_back(
    cleanup: LabelCleanup, web_database: Database
) -> None:
    repo = SettingsRepository(web_database)

    stored = await repo.write(CLEANUP_POLICY, cleanup, 0, ACTOR)

    assert stored.cleanup == cleanup
    assert (await repo.read()).cleanup == cleanup


@pytest.mark.parametrize("cleanup", OUT_OF_RANGE_CLEANUPS, ids=repr)
async def test_given_cleanup_numbers_outside_the_range_when_written_then_the_database_check_refuses_them(
    cleanup: LabelCleanup, web_database: Database
) -> None:
    repo = SettingsRepository(web_database)

    with pytest.raises(DBAPIError):
        await repo.write(CLEANUP_POLICY, cleanup, 0, ACTOR)

    assert (await repo.read()).version == 0
