from datetime import UTC, datetime, timedelta

import pytest

from app.clock import SystemClock
from app.codes import SecretsCodeSource
from app.ids import SecretsIdSource
from tests.fakes import FakeClock, FakeCodes, FakeIds

URL_SAFE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_system_clock_is_aware_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_fake_clock_returns_what_was_set_and_moves_only_when_told() -> None:
    start = datetime(2030, 5, 6, 7, 8, 9, tzinfo=UTC)
    clock = FakeClock(start)
    assert clock.now() == start
    assert clock.now() == start
    clock.advance(timedelta(seconds=60))
    assert clock.now() == start + timedelta(seconds=60)
    clock.set(start)
    assert clock.now() == start


def test_tokens_are_distinct_url_safe_and_43_chars() -> None:
    ids = SecretsIdSource()
    tokens = {ids.token(32) for _ in range(1000)}
    assert len(tokens) == 1000
    assert all(len(t) == 43 and set(t) <= URL_SAFE for t in tokens)


def test_tokens_come_from_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_token_urlsafe(nbytes: int) -> str:
        calls.append(nbytes)
        return "x" * 43

    monkeypatch.setattr("app.ids.secrets.token_urlsafe", fake_token_urlsafe)
    ids = SecretsIdSource()
    assert ids.token(32) == "x" * 43
    ids.session_id()
    ids.login_request_id()
    ids.request_id()
    assert calls == [32, 32, 32, 32]


def test_named_ids_are_distinct_and_43_chars() -> None:
    ids = SecretsIdSource()
    values = {ids.session_id(), ids.login_request_id(), ids.request_id()}
    assert len(values) == 3
    assert all(len(v) == 43 for v in values)


def test_fake_ids_count() -> None:
    ids = FakeIds()
    assert ids.session_id() == "session-1"
    assert ids.login_request_id() == "login-2"
    assert ids.request_id() == "request-3"
    assert ids.token(32) == "token32-4"


def test_codes_are_six_digits_with_leading_zeros() -> None:
    codes = SecretsCodeSource()
    produced = [codes.six_digits() for _ in range(10000)]
    assert all(len(c) == 6 and c.isascii() and c.isdigit() for c in produced)
    assert any(int(c) < 100000 for c in produced)


def test_codes_pad_small_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_randbelow(_exclusive_upper_bound: int) -> int:
        return 42

    monkeypatch.setattr("app.codes.secrets.randbelow", fake_randbelow)
    assert SecretsCodeSource().six_digits() == "000042"


def test_fake_codes_script_then_error() -> None:
    codes = FakeCodes(["123456", "654321"])
    assert codes.six_digits() == "123456"
    assert codes.six_digits() == "654321"
    with pytest.raises(AssertionError, match="exhausted"):
        codes.six_digits()
