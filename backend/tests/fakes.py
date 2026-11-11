from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from pydantic import SecretStr

from app.config import Settings
from app.main import build_app


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


class FakeMailer:
    """Recording mailer: remembers every code it was asked to send."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, datetime]] = []

    async def send_code(self, address: str, code: str, expires_at: datetime) -> None:
        self.sent.append((address, code, expires_at))

    def fail(self) -> None:
        """Make every following send fail with MailError."""
        raise NotImplementedError

    def succeed(self) -> None:
        """Make the following sends work again."""
        raise NotImplementedError


def make_settings(**overrides: object) -> Settings:
    """Return a complete valid configuration; keyword arguments replace single fields."""
    values: dict[str, object] = {
        "environment": "test",
        "username": "test-user",
        "email_address": "marco@example.test",
        "smtp_host": "smtp.example.test",
        "smtp_port": 587,
        "smtp_user": "test-smtp-user",
        "smtp_password": SecretStr("test-smtp-password"),
        "code_hash_key": SecretStr("a" * 32),
        "csrf_key": SecretStr("b" * 32),
        "username_hash_key": SecretStr("c" * 32),
        "public_origin": "https://settings.example.test",
    }
    values.update(overrides)
    return Settings(**values)  # pyright: ignore[reportArgumentType]


def make_app(settings: Settings | None = None) -> FastAPI:
    """Create the app with fakes for every injected source."""
    return build_app(
        settings or make_settings(), clock=FakeClock(), ids=FakeIds(), codes=FakeCodes([]), mailer=FakeMailer()
    )
