"""The floor of database tests that must run in the backend job (U-web-settings-62, CR-02).

A database test that skips is green. The container fixtures fail instead of skipping when ``CI`` is set, and this
check is the second wall: after the run, the junit report must show at least ``MINIMUM_DB_TESTS`` tests of
``tests/db`` that ran (passed; a skip does not count). ``tests/db/test_start_policy.py`` needs no database and is not
counted.

How the number is kept current: it is about 95 % of what ran when it was last set (70 after U-web-settings-54). The
check also fails when more than ``CEILING_FACTOR`` times the floor ran, and says which number to set, so a floor that
no longer matches the suite cannot go unnoticed in either direction.

Use: ``python -m tests.db_floor <junit.xml>``; exit status 1 with the reason when the check fails.
"""

import sys
from pathlib import Path
from typing import Final
from xml.etree import ElementTree  # the report is written by pytest in the same job, not input from outside

MINIMUM_DB_TESTS: Final = 66
CEILING_FACTOR: Final = 1.25
_DB_PREFIX: Final = "tests.db."
_NO_DATABASE: Final = frozenset({"tests.db.test_start_policy"})


def count_ran(report: Path) -> int:
    """Count the database tests of a junit report that ran: in ``tests/db``, not skipped, not failed or errored."""
    # The report is this job's own pytest output, not input from outside.
    root = ElementTree.parse(report).getroot()  # noqa: S314  # nosemgrep: python.lang.security.use-defused-xml-parse.use-defused-xml-parse
    ran = 0
    for case in root.iter("testcase"):
        module = case.get("classname", "")
        if not module.startswith(_DB_PREFIX) or module in _NO_DATABASE:
            continue
        if case.find("skipped") is None and case.find("failure") is None and case.find("error") is None:
            ran += 1
    return ran


def check(report: Path) -> str | None:
    """Return why the report fails the floor, or None.

    Args:
        report: The junit report of the backend run.

    Returns:
        The reason, or None when the number of database tests that ran is within the floor and its ceiling.
    """
    ran = count_ran(report)
    if ran < MINIMUM_DB_TESTS:
        return f"{ran} database tests ran, at least {MINIMUM_DB_TESTS} must (are they skipped?)"
    if ran > MINIMUM_DB_TESTS * CEILING_FACTOR:
        return f"{ran} database tests ran, far above {MINIMUM_DB_TESTS}: raise MINIMUM_DB_TESTS to {int(ran * 0.95)}"
    return None


if __name__ == "__main__":
    problem = check(Path(sys.argv[1]))
    if problem is not None:
        print(f"::error::{problem}")
        sys.exit(1)
