"""U-web-settings-38: the From address is its own setting, not the SMTP user (the chart passes APP_SMTP_FROM)."""

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.mail.smtp import SmtpMailSender
from app.startup import validate_startup
from tests.fakes import FakeClock, make_settings
from tests.mail.smtp_server import HOST, PASSWORD, USER, Authority, smtp_server
from tests.test_startup import refused_fields


@pytest.mark.parametrize("address", ["", "not-an-address", "a@b@c", "a@b.test\r\nBcc: x@y.test"])
def test_given_a_missing_or_wrong_from_address_when_checked_then_refused_naming_smtp_from(address: str) -> None:
    assert refused_fields(smtp_from=address) == ("smtp_from",)


def test_given_a_valid_from_address_when_checked_then_accepted() -> None:
    validate_startup(make_settings(smtp_from="assistant@example.test"))


def test_given_a_from_address_when_a_code_is_sent_then_the_message_comes_from_it_and_not_from_the_user(
    tmp_path: Path,
) -> None:
    authority = Authority.create("test CA")
    with smtp_server(authority.issue(tmp_path, dns_name=None, ip=HOST)) as (port, received):
        settings = make_settings(
            smtp_host=HOST,
            smtp_port=port,
            smtp_user=USER,
            smtp_password=SecretStr(PASSWORD),
            smtp_from="assistant@example.test",
        )
        sender = SmtpMailSender(settings, FakeClock(), tls_context=authority.client_context())
        asyncio.run(sender.send_code("marco@example.test", "123456", FakeClock().now() + timedelta(minutes=10)))

    content = received.messages[0]
    assert "From: assistant@example.test" in content
    assert f"From: {USER}" not in content
