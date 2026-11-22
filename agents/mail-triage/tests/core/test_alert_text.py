"""U-12: alert text and buttons (spec AC-3, AC-16, AC-21, AC-23; guardrail-telegram)."""

from __future__ import annotations

from app.core.alert_decision import AlertCause, CauseKind
from app.core.alert_text import (
    MAX_MESSAGE_CHARS,
    AlertBasis,
    DigestEntry,
    MailMeta,
    build_alert,
    build_digest,
)
from app.core.judgement import Judgement

JUDGEMENT = Judgement(
    topic_id="00000000-0000-0000-0000-00000000000a",
    urgent=True,
    reason="Invoice is due on Friday",
    summary="The supplier asks for payment of EUR 120.",
    confidence=0.9,
)
META = MailMeta(sender="Billing <billing@example.com>", subject="Invoice 42", reply_to=None, has_attachment=False)
URGENT = (AlertCause(CauseKind.URGENT),)
PASS = AlertBasis(URGENT, verified_domain="example.com", by_rule=False)
UNVERIFIED = AlertBasis(URGENT, verified_domain=None, by_rule=False)
TICKED = (AlertCause(CauseKind.ALWAYS_NOTIFY, "Huis/Energie"),)


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


def test_given_an_unauthenticated_sender_when_built_then_a_visible_warning_is_added() -> None:
    assert "Sender not verified" in build_alert("1", META, JUDGEMENT, UNVERIFIED).text
    assert "Sender not verified" not in build_alert("1", META, JUDGEMENT, PASS).text


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

    message = build_alert("1", meta, judgement, UNVERIFIED)

    assert len(message.text) <= MAX_MESSAGE_CHARS
    assert "&amp;" in message.text


def _judgement(**changes: object) -> Judgement:
    return JUDGEMENT.model_copy(update={"urgent": False, **changes})


def test_given_a_ticked_category_when_built_then_the_alert_starts_with_the_label_and_keeps_the_facts() -> None:
    basis = AlertBasis(TICKED, verified_domain="example.com", by_rule=False)

    message = build_alert("9", META, _judgement(), basis)

    assert message.text.startswith("<b>Always notify: Huis/Energie</b>")
    for fact in ("billing@example.com", "Invoice 42", "Invoice is due on Friday", "The supplier asks for payment"):
        assert fact in message.text
    assert [button.data for button in message.buttons] == ["reply:9", "later:9", "stop:9"]


def test_given_an_urgent_alert_when_built_then_it_starts_with_the_urgency_label() -> None:
    assert build_alert("1", META, JUDGEMENT, PASS).text.startswith("<b>Urgent: needs your attention</b>")


def test_given_urgent_and_two_ticked_categories_when_built_then_every_cause_is_named() -> None:
    causes = (*URGENT, AlertCause(CauseKind.ALWAYS_NOTIFY, "A/B"), AlertCause(CauseKind.ALWAYS_NOTIFY, "C"))

    text = build_alert("1", META, JUDGEMENT, AlertBasis(causes, "example.com", by_rule=False)).text

    assert text.startswith("<b>Urgent: needs your attention</b>")
    assert "Also: Always notify: A/B" in text
    assert "Also: Always notify: C" in text


def test_given_a_sender_rule_when_built_then_it_shows_the_domain_and_no_summary_and_no_link() -> None:
    meta = MailMeta("billing@energie.example.nl", "Invoice https://evil.example/x", reply_to=None, has_attachment=False)
    basis = AlertBasis(TICKED, verified_domain="energie.example.nl", by_rule=True)

    text = build_alert("1", meta, _judgement(reason="Sender rule: energie.example.nl"), basis).text

    assert "energie.example.nl" in text
    assert "content not checked by the model" in text.casefold()
    assert "Summary" not in text
    assert "The supplier asks for payment" not in text
    assert "<a " not in text
    assert "<code>billing@energie.example.nl</code>" in text  # a code span is never made clickable by Telegram
    assert "<code>Invoice https://evil.example/x</code>" in text


def test_given_a_model_filed_ticked_mail_without_an_authenticated_sender_when_built_then_it_shows_the_address() -> None:
    meta = MailMeta("CEO <attacker@example.net>", "Pay now", reply_to=None, has_attachment=False)
    basis = AlertBasis(TICKED, verified_domain=None, by_rule=False)

    text = build_alert("1", meta, _judgement(), basis).text

    assert "Sender not verified" in text
    assert "attacker@example.net" in text


def test_given_a_missing_or_unparsable_from_when_built_then_it_says_sender_not_verified() -> None:
    meta = MailMeta("", "Pay now", reply_to=None, has_attachment=False)

    text = build_alert("1", meta, _judgement(), AlertBasis(TICKED, None, by_rule=False)).text

    assert "Sender not verified" in text
    assert "no readable From address" in text


def test_given_a_digest_of_always_notify_mail_when_built_then_it_does_not_call_them_urgent() -> None:
    entries = [DigestEntry("a@example.com", "s")]

    assert "urgent" not in build_digest(entries, held=False).text
    assert "urgent" not in build_digest(entries, held=True).text
