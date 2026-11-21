"""The EHLO name comes from the From address, so sending never waits for a slow ``socket.getfqdn()`` lookup."""

import asyncio
import socket
from datetime import timedelta
from pathlib import Path

import aiosmtplib
import pytest
from pydantic import SecretStr

from app.mail.smtp import SmtpMailSender
from tests.fakes import FakeClock, make_settings
from tests.mail.smtp_server import HOST, PASSWORD, USER, Authority, smtp_server


def test_given_a_slow_hostname_lookup_when_a_code_is_sent_then_the_ehlo_name_is_the_from_domain_and_no_lookup_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def lookup_that_must_not_run(name: str = "") -> str:
        raise AssertionError("socket.getfqdn was called; on some networks it takes seconds")

    seen: list[str | None] = []
    real_send = aiosmtplib.send

    async def spy(*args: object, **kwargs: object) -> object:
        local_hostname = kwargs.get("local_hostname")
        seen.append(local_hostname if isinstance(local_hostname, str) else None)
        return await real_send(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(socket, "getfqdn", lookup_that_must_not_run)
    monkeypatch.setattr(aiosmtplib, "send", spy)
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

    assert seen == ["example.test"]
    assert len(received.messages) == 1
