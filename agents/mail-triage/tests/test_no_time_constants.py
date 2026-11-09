"""U-quiet-hours-03 criterion 10: the first-release time constants are gone from the app."""

from __future__ import annotations

import re
from pathlib import Path

CONSTANTS = re.compile(r"\b(TIME_ZONE|QUIET_START|QUIET_END|OVERVIEW_AT|TOMORROW_AT)\b")
APP = Path(__file__).resolve().parents[1] / "app"
# The alert state machine has an event called QUIET_END ("quiet hours are over"); it is not a time constant.
ALERT_EVENT = ("core/alert_state.py", "QUIET_END")


def test_given_the_app_sources_when_searched_then_no_time_constant_is_left_outside_the_policy_code() -> None:
    hits = {
        (path.relative_to(APP).as_posix(), match.group(1))
        for path in APP.rglob("*.py")
        for match in CONSTANTS.finditer(path.read_text(encoding="utf-8"))
    }

    assert hits - {ALERT_EVENT} == set()
