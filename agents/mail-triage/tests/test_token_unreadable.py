"""U-76: an undecryptable stored token stops the agent with the "no consent" exit code and an actionable message."""

from __future__ import annotations

import logging

import pytest

from app.adapters.token_store import TokenDecryptError
from app.wiring import EXIT_NO_CONSENT, load_token_or_stop

REFRESH = "1//0g-refresh-token-value"
KEY = "the-token-encryption-key-value"


class Store:
    def __init__(self, *, token: str | None = None, error: Exception | None = None) -> None:
        self._token, self._error = token, error

    async def load(self) -> str | None:
        if self._error is not None:
            raise self._error
        return self._token


async def test_given_a_readable_token_when_loaded_then_it_is_returned() -> None:
    assert await load_token_or_stop(Store(token=REFRESH)) == REFRESH


async def test_given_no_token_when_loaded_then_the_no_consent_exit_code_is_returned(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR):
        assert await load_token_or_stop(Store()) == EXIT_NO_CONSENT == 3

    assert "python -m app.consent" in caplog.text


async def test_given_an_undecryptable_token_when_loaded_then_it_stops_with_exit_3_and_names_the_way_out(
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = TokenDecryptError(f"could not decrypt {REFRESH} with {KEY}")  # a message that must never be logged

    with caplog.at_level(logging.DEBUG):
        result = await load_token_or_stop(Store(error=error))

    assert result == EXIT_NO_CONSENT
    assert (
        "the stored Gmail token cannot be decrypted with the current TOKEN_ENCRYPTION_KEY: "
        "run node scripts/local-stack.mjs consent"
    ) in caplog.text
    for secret in (REFRESH, KEY):
        assert secret not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)  # no traceback either


async def test_given_another_failure_when_loaded_then_it_is_not_swallowed() -> None:
    with pytest.raises(RuntimeError):
        await load_token_or_stop(Store(error=RuntimeError("database down")))
