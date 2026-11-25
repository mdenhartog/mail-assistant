"""The agent reads its limits from category-policy: no second copy of a number that the policy owns (ADR-0060)."""

from __future__ import annotations

from app.adapters import judge_anthropic
from app.db.models import Base
from category_policy import (
    DESCRIPTION_MAX,
    INSTRUCTIONS_MAX,
    LABEL_MAX,
    PROTECTION_DAYS_MAX,
    PROTECTION_DAYS_MIN,
    RETENTION_DAYS_MAX,
    RETENTION_DAYS_MIN,
    WAIT_MINUTES_MAX,
    WAIT_MINUTES_MIN,
)


def check_texts() -> dict[str, str]:
    return {
        str(c.name): str(c.sqltext)
        for table in Base.metadata.tables.values()
        for c in table.constraints
        if c.name is not None and hasattr(c, "sqltext")
    }


def test_given_the_judge_limits_when_read_then_they_are_the_policy_limits() -> None:
    assert judge_anthropic.NAME_MAX_CHARS == LABEL_MAX
    assert judge_anthropic.DESCRIPTION_MAX_CHARS == DESCRIPTION_MAX
    assert judge_anthropic.INSTRUCTIONS_MAX_CHARS == INSTRUCTIONS_MAX


def test_given_the_check_constraints_when_read_then_they_carry_the_policy_bounds() -> None:
    texts = check_texts()

    assert f"BETWEEN {WAIT_MINUTES_MIN} AND {WAIT_MINUTES_MAX}" in texts["ck_schedule_label_wait"]
    assert f"BETWEEN {WAIT_MINUTES_MIN} AND {WAIT_MINUTES_MAX}" in texts["ck_label_empty_since_wait"]
    assert f"BETWEEN {PROTECTION_DAYS_MIN} AND {PROTECTION_DAYS_MAX}" in texts["ck_schedule_label_protection"]
    assert f"BETWEEN {RETENTION_DAYS_MIN} AND {RETENTION_DAYS_MAX}" in texts["ck_schedule_label_retention"]
    assert f"BETWEEN 1 AND {LABEL_MAX}" in texts["ck_category_name_length"]
    assert f"<= {DESCRIPTION_MAX}" in texts["ck_category_description_length"]
    assert f"BETWEEN 1 AND {LABEL_MAX}" in texts["ck_list_settings_archive_label"]
    assert f"<= {INSTRUCTIONS_MAX}" in texts["ck_list_settings_instructions"]
