import asyncio
import logging
import ssl
import time
import traceback
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.mail.sender import MailError
from app.mail.smtp import SmtpMailSender
from tests.fakes import FakeClock, make_settings
from tests.mail.smtp_server import HOST, PASSWORD, USER, Authority, free_port, smtp_server

ADDRESS = "canary-recipient@example.test"
CODE = "424242"


@pytest.fixture(scope="module")
def authority() -> Authority:
    return Authority.create("test CA")


def _sender(port: int, context: ssl.SSLContext, *, timeout: float = 5.0, password: str = PASSWORD) -> SmtpMailSender:
    settings = make_settings(
        smtp_host=HOST,
        smtp_port=port,
        smtp_user=USER,
        smtp_password=SecretStr(password),
        smtp_timeout_seconds=timeout,
    )
    clock = FakeClock()
    return SmtpMailSender(settings, clock, tls_context=context)


async def _send(sender: SmtpMailSender) -> None:
    clock_now = FakeClock().now()
    await sender.send_code(ADDRESS, CODE, clock_now + timedelta(minutes=10))


def _texts(error: BaseException) -> str:
    return " | ".join([str(error), repr(error), "".join(traceback.format_exception(error))])


def _assert_clean(error: BaseException, *, reply_marker: str = "") -> None:
    text = _texts(error)
    for forbidden in (ADDRESS, CODE, PASSWORD, USER, "535", "Authentication", reply_marker):
        if forbidden:
            assert forbidden not in text
    assert error.__cause__ is None
    assert error.__context__ is None


def test_happy_path_arrives_after_the_upgrade_and_credentials_follow_it(authority: Authority, tmp_path: Path) -> None:
    server_context = authority.issue(tmp_path, dns_name=None, ip=HOST)
    with smtp_server(server_context) as (port, received):
        asyncio.run(_send(_sender(port, authority.client_context())))
    assert received.events == ["auth:tls", "data:tls"]
    assert received.logins == [(USER, PASSWORD)]
    assert len(received.messages) == 1
    assert CODE in received.messages[0]
    assert "valid for 10 minutes" in received.messages[0]
    assert "http" not in received.messages[0].lower()
    subject = next(line for line in received.messages[0].splitlines() if line.lower().startswith("subject:"))
    assert CODE not in subject


def test_server_without_starttls_is_refused_and_nothing_is_sent(authority: Authority) -> None:
    with smtp_server(None) as (port, received), pytest.raises(MailError) as caught:
        asyncio.run(_send(_sender(port, authority.client_context())))
    assert received.events == []
    assert received.logins == []
    assert received.messages == []
    _assert_clean(caught.value)


def test_certificate_from_an_untrusted_ca_is_refused(authority: Authority, tmp_path: Path) -> None:
    other = Authority.create("other CA")
    with smtp_server(other.issue(tmp_path, dns_name=None, ip=HOST)) as (port, received), pytest.raises(MailError) as e:
        asyncio.run(_send(_sender(port, authority.client_context())))
    assert received.events == []
    _assert_clean(e.value)


def test_certificate_for_another_host_name_is_refused(authority: Authority, tmp_path: Path) -> None:
    with (
        smtp_server(authority.issue(tmp_path, dns_name="other.example.test", ip=None)) as (port, received),
        pytest.raises(MailError) as caught,
    ):
        asyncio.run(_send(_sender(port, authority.client_context())))
    assert received.events == []
    _assert_clean(caught.value)


def test_refused_login_gives_a_clean_mail_error(authority: Authority, tmp_path: Path) -> None:
    with (
        smtp_server(authority.issue(tmp_path, dns_name=None, ip=HOST), accept_login=False) as (port, received),
        pytest.raises(MailError) as caught,
    ):
        asyncio.run(_send(_sender(port, authority.client_context())))
    assert received.messages == []
    _assert_clean(caught.value)


@asynccontextmanager
async def _raw_server(*, close_at_once: bool) -> AsyncGenerator[int]:
    async def handle(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if close_at_once:
            writer.close()
            return
        await asyncio.sleep(30)

    port = free_port()
    server = await asyncio.start_server(handle, HOST, port)
    try:
        yield port
    finally:
        server.close()


async def test_dropped_connection_gives_a_clean_mail_error(authority: Authority) -> None:
    async with _raw_server(close_at_once=True) as port:
        with pytest.raises(MailError) as caught:
            await _send(_sender(port, authority.client_context()))
    _assert_clean(caught.value)


async def test_stalling_server_ends_at_the_timeout_with_a_clean_mail_error(authority: Authority) -> None:
    async with _raw_server(close_at_once=False) as port:
        started = time.monotonic()
        with pytest.raises(MailError) as caught:
            await _send(_sender(port, authority.client_context(), timeout=0.5))
        elapsed = time.monotonic() - started
    assert 0.4 <= elapsed < 3
    _assert_clean(caught.value)


def test_stall_after_the_greeting_also_ends_at_the_timeout(authority: Authority, tmp_path: Path) -> None:
    with smtp_server(authority.issue(tmp_path, dns_name=None, ip=HOST), stall=True) as (port, _received):
        started = time.monotonic()
        with pytest.raises(MailError):
            asyncio.run(_send(_sender(port, authority.client_context(), timeout=1.0)))
        assert time.monotonic() - started < 5


def test_failing_send_leaves_no_canary_in_the_logs(
    authority: Authority, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    server = smtp_server(authority.issue(tmp_path, dns_name=None, ip=HOST), accept_login=False)
    with server as (port, _received), pytest.raises(MailError):
        asyncio.run(_send(_sender(port, authority.client_context(), password=PASSWORD)))
    text = "\n".join(logging.Formatter().format(record) for record in caplog.records)
    for canary in (CODE, PASSWORD, ADDRESS):
        assert canary not in text
    assert logging.getLogger("aiosmtplib").level == logging.WARNING


def test_a_context_that_does_not_verify_is_refused() -> None:
    insecure = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    insecure.check_hostname = False
    insecure.verify_mode = ssl.CERT_NONE
    with pytest.raises(ValueError, match="verify"):
        SmtpMailSender(make_settings(), FakeClock(), tls_context=insecure)
