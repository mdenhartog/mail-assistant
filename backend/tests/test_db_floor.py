"""U-web-settings-62, criterion 2 (CR-02): the backend job fails when fewer database tests ran than the floor."""

from pathlib import Path

import pytest

from tests.db_floor import MINIMUM_DB_TESTS, check, count_ran

DB = "tests.db.test_settings_repo"
CASE = '<testcase classname="{module}" name="t{index}">{outcome}</testcase>'


def _report(tmp_path: Path, *groups: tuple[str, str, int]) -> Path:
    """A junit report from (module, outcome element, number of cases) groups."""
    cases = [
        CASE.format(module=module, index=f"{module}{outcome}{i}", outcome=outcome)
        for module, outcome, number in groups
        for i in range(number)
    ]
    path = tmp_path / "junit.xml"
    path.write_text(f"<testsuites><testsuite>{''.join(cases)}</testsuite></testsuites>", encoding="utf-8")
    return path


def test_given_a_report_when_counted_then_only_database_tests_that_ran_count(tmp_path: Path) -> None:
    report = _report(
        tmp_path,
        (DB, "", 7),
        (DB, "<skipped/>", 3),
        (DB, "<failure/>", 1),
        ("tests.test_limits", "", 50),
        ("tests.db.test_start_policy", "", 19),
    )

    assert count_ran(report) == 7  # skips, failures, other directories and the policy tests (no database) do not count


def test_given_every_database_test_skipped_when_checked_then_the_job_fails(tmp_path: Path) -> None:
    report = _report(tmp_path, (DB, "<skipped/>", 70), ("tests.test_limits", "", 500))

    message = check(report)

    assert message is not None
    assert "0 database tests ran" in message


def test_given_one_below_the_floor_when_checked_then_it_fails_and_at_the_floor_it_passes(tmp_path: Path) -> None:
    assert check(_report(tmp_path, (DB, "", MINIMUM_DB_TESTS - 1))) is not None
    assert check(_report(tmp_path, (DB, "", MINIMUM_DB_TESTS))) is None


def test_given_far_more_tests_than_the_floor_when_checked_then_it_fails_so_the_floor_is_raised(tmp_path: Path) -> None:
    message = check(_report(tmp_path, (DB, "", MINIMUM_DB_TESTS * 2)))

    assert message is not None
    assert "raise MINIMUM_DB_TESTS" in message


def test_given_a_missing_report_when_checked_then_it_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        check(tmp_path / "absent.xml")
