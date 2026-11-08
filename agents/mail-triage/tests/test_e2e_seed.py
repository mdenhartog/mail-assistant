"""U-19: the seed mails for the manual end-to-end run (no real accounts are used by this test)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "e2e_seed.py"
spec = importlib.util.spec_from_file_location("e2e_seed", SCRIPT)
assert spec is not None
assert spec.loader is not None
seed = importlib.util.module_from_spec(spec)
sys.modules["e2e_seed"] = seed
spec.loader.exec_module(seed)


def test_given_the_seed_when_listed_then_it_covers_the_four_cases_of_the_runbook() -> None:
    kinds = [mail.kind for mail in seed.MAILS]

    assert kinds == ["personal-request", "newsletter", "automatic-notice", "injection"]
    assert all(mail.subject.startswith("[mail-triage e2e] ") for mail in seed.MAILS)


def test_given_the_seed_when_read_then_the_injection_mail_asks_for_harmful_actions_and_the_rest_do_not() -> None:
    injected = next(mail for mail in seed.MAILS if mail.kind == "injection")

    assert "delete" in injected.body.lower()
    assert "send" in injected.body.lower()
    assert all("delete" not in m.body.lower() for m in seed.MAILS if m.kind != "injection")


def test_given_the_automatic_notice_when_read_then_it_carries_the_headers_that_forbid_a_reply() -> None:
    notice = next(mail for mail in seed.MAILS if mail.kind == "automatic-notice")

    assert notice.headers["Auto-Submitted"] == "auto-generated"


def test_given_the_seed_when_rendered_then_each_mail_is_a_complete_message_for_the_test_mailbox() -> None:
    raw = seed.render("test.mailbox@example.com", "sender@example.org")

    assert len(raw) == 4
    for message in raw:
        assert "To: test.mailbox@example.com" in message
        assert "From: sender@example.org" in message
    assert "Auto-Submitted: auto-generated" in raw[2]
