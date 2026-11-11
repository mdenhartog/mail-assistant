from datetime import UTC, datetime, timedelta


class FakeClock:
    """Settable clock: returns what was set and moves only when told to."""

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now if now is not None else datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        self._now = now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


class FakeIds:
    """Counting id source: every call returns the next predictable value."""

    def __init__(self) -> None:
        self._count = 0

    def _next(self, prefix: str) -> str:
        self._count += 1
        return f"{prefix}-{self._count}"

    def token(self, nbytes: int) -> str:
        return self._next(f"token{nbytes}")

    def session_id(self) -> str:
        return self._next("session")

    def login_request_id(self) -> str:
        return self._next("login")

    def request_id(self) -> str:
        return self._next("request")


class FakeCodes:
    """Scripted code source: returns the given codes in order, then raises."""

    def __init__(self, codes: list[str]) -> None:
        self._codes = list(codes)

    def six_digits(self) -> str:
        if not self._codes:
            msg = "FakeCodes script is exhausted"
            raise AssertionError(msg)
        return self._codes.pop(0)
