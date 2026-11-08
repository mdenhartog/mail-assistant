"""U-07: encrypted refresh-token store (spec AC-25; ADR-0011)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.adapters.token_store import TokenCipher, TokenDecryptError, TokenKeyError, TokenStore

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

REFRESH = "1//0g-very-secret-refresh-token"


def new_key() -> SecretStr:
    return SecretStr(Fernet.generate_key().decode())


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    yield engine
    await engine.dispose()


def store_with(engine: AsyncEngine, key: SecretStr) -> TokenStore:
    return TokenStore(async_sessionmaker(engine, expire_on_commit=False), TokenCipher(key))


def test_given_a_token_when_encrypted_then_it_decrypts_to_the_original_and_the_bytes_hide_it() -> None:
    cipher = TokenCipher(new_key())

    sealed = cipher.encrypt(REFRESH)

    assert REFRESH.encode() not in sealed
    assert cipher.decrypt(sealed) == REFRESH
    assert cipher.encrypt(REFRESH) != sealed  # a fresh nonce each time


@pytest.mark.parametrize("bad", ["", "short", "not base64 !!!", "a" * 44])
def test_given_a_missing_or_malformed_key_when_the_cipher_is_built_then_it_fails_closed(bad: str) -> None:
    with pytest.raises(TokenKeyError) as caught:
        TokenCipher(SecretStr(bad))

    assert bad not in str(caught.value) or bad == ""


def test_given_tampered_or_foreign_ciphertext_when_decrypted_then_it_fails_with_no_partial_value() -> None:
    cipher = TokenCipher(new_key())
    sealed = bytearray(cipher.encrypt(REFRESH))
    sealed[-3] ^= 0x01

    with pytest.raises(TokenDecryptError):
        cipher.decrypt(bytes(sealed))
    with pytest.raises(TokenDecryptError):
        TokenCipher(new_key()).decrypt(cipher.encrypt(REFRESH))


async def test_given_a_refresh_token_when_saved_and_loaded_then_it_round_trips(engine: AsyncEngine) -> None:
    store = store_with(engine, new_key())

    assert await store.load() is None
    await store.save(REFRESH)

    assert await store.load() == REFRESH


async def test_given_the_database_when_read_directly_then_neither_the_token_nor_the_key_is_there(
    engine: AsyncEngine,
) -> None:
    key = new_key()
    await store_with(engine, key).save(REFRESH)

    async with engine.connect() as connection:
        rows = (await connection.execute(text("select ciphertext from oauth_token"))).all()
        dump = (await connection.execute(text("select row_to_json(t)::text from oauth_token t"))).scalar_one()

    assert len(rows) == 1
    assert REFRESH.encode() not in bytes(rows[0][0])
    assert REFRESH not in dump
    assert key.get_secret_value() not in dump
    assert key.get_secret_value().encode() not in bytes(rows[0][0])


async def test_given_a_wrong_key_when_loading_then_it_fails_closed(engine: AsyncEngine) -> None:
    await store_with(engine, new_key()).save(REFRESH)

    with pytest.raises(TokenDecryptError) as caught:
        await store_with(engine, new_key()).load()

    assert REFRESH not in str(caught.value)


async def test_given_two_saves_when_loading_then_there_is_one_row_with_the_latest_token(engine: AsyncEngine) -> None:
    key = new_key()
    store = store_with(engine, key)

    await store.save("first")
    await store.save("second")

    assert await store.load() == "second"
    async with engine.connect() as connection:
        assert (await connection.execute(text("select count(*) from oauth_token"))).scalar_one() == 1


async def test_given_an_empty_token_when_saved_then_it_is_refused(engine: AsyncEngine) -> None:
    with pytest.raises(ValueError, match="empty"):
        await store_with(engine, new_key()).save("  ")
