import logging

import pytest

from tests.conftest import CANARIES, find_canaries


def _record(logger: str, message: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord(logger, logging.INFO, __file__, 1, message, args or None, None)


@pytest.mark.parametrize("canary", CANARIES)
def test_check_names_the_canary_and_the_logger(canary: str) -> None:
    findings = find_canaries([_record("app.signin", "user %s did something", canary)])
    assert findings == [f"canary {canary!r} in a record of logger 'app.signin'"]


def test_check_covers_the_four_canaries() -> None:
    assert set(CANARIES) == {"canary-user", "424242", "Pacific/Kiritimati", "canary-smtp-secret"}


def test_check_passes_without_a_canary() -> None:
    assert find_canaries([_record("app.signin", "sign-in code sent")]) == []


def test_logging_a_canary_in_a_test_is_captured_by_the_shared_handler(
    canary_log_records: list[logging.LogRecord],
) -> None:
    logging.getLogger("app.probe").info("zone is %s", "Pacific/Kiritimati")
    assert find_canaries(canary_log_records) == ["canary 'Pacific/Kiritimati' in a record of logger 'app.probe'"]
    canary_log_records.clear()
