from datetime import UTC, datetime

import pytest

from app.mail.sender import MailError, MailSender
from tests.fakes import FakeMailer

EXPIRY = datetime(2026, 1, 1, 12, 10, tzinfo=UTC)


async def test_fake_records_address_code_and_expiry() -> None:
    fake = FakeMailer()
    sender: MailSender = fake
    await sender.send_code("marco@example.test", "424242", EXPIRY)
    assert fake.sent == [("marco@example.test", "424242", EXPIRY)]


async def test_fake_can_be_told_to_fail_and_records_nothing() -> None:
    fake = FakeMailer()
    fake.fail()
    with pytest.raises(MailError):
        await fake.send_code("marco@example.test", "424242", EXPIRY)
    assert fake.sent == []


async def test_fake_can_recover_after_failing() -> None:
    fake = FakeMailer()
    fake.fail()
    fake.succeed()
    await fake.send_code("marco@example.test", "424242", EXPIRY)
    assert len(fake.sent) == 1
