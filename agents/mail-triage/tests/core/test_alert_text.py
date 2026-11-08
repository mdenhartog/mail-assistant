"""U-12: alert text and buttons (spec AC-3, AC-16, AC-21, AC-23; guardrail-telegram)."""

from __future__ import annotations

from app.core.alert_text import (
    MAX_MESSAGE_CHARS,
    AuthResults,
    DigestEntry,
    MailMeta,
    build_alert,
    build_digest,
)
from app.core.judgement import Judgement

JUDGEMENT = Judgement(
    category="Finance",
    urgent=True,
    reason="Invoice is due on Friday",
    summary="The supplier asks for payment of EUR 120.",
    confidence=0.9,
)
META = MailMeta(sender="Billing <billing@example.com>", subject="Invoice 42", reply_to=None, has_attachment=False)
PASS = AuthResults(spf="pass", dkim="pass", dmarc="pass")


def test_given_a_judgement_when_built_then_the_text_has_the_facts_and_exactly_three_buttons() -> None:
    message = build_alert("17", META, JUDGEMENT, PASS)

    for fact in ("billing@example.com", "Invoice 42", "The supplier asks for payment", "Invoice is due on Friday"):
        assert fact in message.text
    assert [button.label for button in message.buttons] == ["Reply", "Remind me later", "No more reminders"]
    assert [button.data for button in message.buttons] == ["reply:17", "later:17", "stop:17"]
    assert all(len(button.data) <= 64 for button in message.buttons)
    assert message.parse_mode == "HTML"


def test_given_markup_and_links_in_the_mail_when_built_then_everything_is_escaped_and_nothing_is_a_link() -> None:
    meta = MailMeta(
        sender='<b>Boss</b> <a href="https://evil.example">boss@example.com</a>',
        subject="<script>alert(1)</script> [click](https://evil.example)",
        reply_to=None,
        has_attachment=False,
    )
    judgement = JUDGEMENT.model_copy(update={"summary": '<a href="https://evil.example">Pay now</a> & more'})

    text = build_alert("1", meta, judgement, PASS).text

    assert "<script>" not in text
    assert "<a " not in text
    assert "&lt;a href=" in text
    assert "&amp; more" in text
    assert "<b>Boss</b>" not in text  # the mail's own tags are shown as text; only our labels are tags


def test_given_a_very_long_subject_and_summary_when_built_then_the_text_is_cut() -> None:
    meta = MailMeta(sender="a@example.com", subject="s" * 5000, reply_to=None, has_attachment=False)
    judgement = JUDGEMENT.model_copy(update={"summary": "m" * 5000, "reason": "r" * 5000})

    text = build_alert("1", meta, judgement, PASS).text

    assert len(text) <= MAX_MESSAGE_CHARS
    assert "s" * 200 not in text


def test_given_a_reply_to_that_differs_from_from_when_built_then_a_warning_names_both() -> None:
    meta = MailMeta("Boss <boss@example.com>", "Hi", reply_to="Other <attacker@example.net>", has_attachment=False)

    text = build_alert("1", meta, JUDGEMENT, PASS).text

    assert "Reply-To differs" in text
    assert "attacker@example.net" in text
    assert "boss@example.com" in text


def test_given_a_reply_to_equal_to_from_when_built_then_there_is_no_warning() -> None:
    meta = MailMeta("Boss <boss@example.com>", "Hi", reply_to="BOSS@example.com", has_attachment=False)

    assert "Reply-To" not in build_alert("1", meta, JUDGEMENT, PASS).text


def test_given_a_failed_spf_dkim_or_dmarc_when_built_then_a_visible_warning_is_added() -> None:
    for failing in (
        AuthResults("fail", "pass", "pass"),
        AuthResults("pass", "fail", "pass"),
        AuthResults("pass", "pass", "fail"),
    ):
        assert "could not be verified" in build_alert("1", META, JUDGEMENT, failing).text

    assert "could not be verified" not in build_alert("1", META, JUDGEMENT, PASS).text


def test_given_missing_authentication_results_when_built_then_there_is_no_false_alarm_or_crash() -> None:
    text = build_alert("1", META, JUDGEMENT, AuthResults(None, None, None)).text

    assert "could not be verified" not in text


def test_given_an_attachment_when_built_then_it_says_so_and_shows_nothing_of_it() -> None:
    meta = MailMeta("a@example.com", "Hi", reply_to=None, has_attachment=True)

    text = build_alert("1", meta, JUDGEMENT, PASS).text

    assert "has an attachment" in text
    assert "has an attachment" not in build_alert("1", META, JUDGEMENT, PASS).text


def test_given_several_alerts_when_a_digest_is_built_then_it_lists_them_with_the_count_and_no_buttons() -> None:
    entries = [DigestEntry(sender=f"s{i}@example.com", subject=f"Subject {i}") for i in range(3)]

    message = build_digest(entries, held=False)

    assert "3" in message.text
    assert "s1@example.com" in message.text
    assert message.buttons == ()


def test_given_a_huge_digest_when_built_then_it_stays_within_the_message_limit_and_escapes() -> None:
    entries = [DigestEntry(sender="<b>x</b>@example.com", subject="y" * 300) for _ in range(200)]

    message = build_digest(entries, held=True)

    assert len(message.text) <= MAX_MESSAGE_CHARS
    assert "<b>x</b>" not in message.text
    assert "while you were away" in message.text


def test_given_fields_that_grow_when_escaped_then_the_alert_still_fits_in_one_message() -> None:
    meta = MailMeta(sender="&" * 500, subject="&" * 500, reply_to=None, has_attachment=True)
    judgement = JUDGEMENT.model_copy(update={"summary": "&" * 400, "reason": "&" * 200})

    message = build_alert("1", meta, judgement, AuthResults("fail", None, None))

    assert len(message.text) <= MAX_MESSAGE_CHARS
    assert "&amp;" in message.text
