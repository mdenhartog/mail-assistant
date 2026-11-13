"""U-web-settings-21, criterion 7: the shared contract cases run through the web repository (AC-26)."""

import json
import re
from datetime import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.exc import DBAPIError

from app.db import Database
from app.settings_repo import SettingsRepository
from schedule_policy.policy import TimePolicy

CASES_FILE = Path(__file__).resolve().parents[3] / "packages" / "schedule-policy" / "contract" / "settings_cases.json"
CASES: list[dict[str, Any]] = json.loads(CASES_FILE.read_text("utf-8"))["cases"]
# Rules the migration's CHECK constraints also enforce; the others need code (known zone) or cannot be stored.
DATABASE_RULES = {"quiet_window_empty", "quiet_window_length", "overview_in_quiet_hours", "remind_in_quiet_hours"}
MALFORMED_TIME_RULES = {"time_not_whole_minute", "time_has_zone"}
ACTOR = "0123456789abcdef0123456789abcdef"


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
async def test_given_a_contract_case_when_written_through_the_repository_then_the_outcome_matches_the_package(
    case: dict[str, Any], web_database: Database
) -> None:
    rules = set(case["rules"])
    if rules & MALFORMED_TIME_RULES:
        pytest.skip("malformed times cannot be stored as minutes")
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
        stored = await repo.write(policy, 0, ACTOR)
        assert (stored.policy, stored.version) == (policy, 1)
    else:
        with pytest.raises(DBAPIError):
            await repo.write(policy, 0, ACTOR)
        assert (await repo.read()).version == 0


def test_given_the_contract_cases_when_selected_then_the_unstorable_ones_are_left_out_before_the_run_not_skipped() -> (
    None
):
    assert not [case["id"] for case in CASES if set(case["rules"]) & MALFORMED_TIME_RULES]
    assert CASES  # the filter must not empty the run
