"""U-label-structure-10: the pure decision of the always-notify alert (ADR-0057; AC-20, AC-23, AC-27)."""

from __future__ import annotations

from app.core.alert_decision import (
    URGENT_LABEL,
    AlertCause,
    CauseKind,
    decide_alert,
    decode_causes,
    encode_causes,
)


def test_given_a_non_urgent_mail_in_a_ticked_category_when_decided_then_one_always_notify_cause() -> None:
    decision = decide_alert(urgent=False, ticked=["Huis/Energie"])

    assert decision is not None
    assert decision.causes == (AlertCause(CauseKind.ALWAYS_NOTIFY, "Huis/Energie"),)
    assert decision.label == "Always notify: Huis/Energie"


def test_given_an_unticked_non_urgent_mail_when_decided_then_there_is_no_alert() -> None:
    assert decide_alert(urgent=False, ticked=[]) is None


def test_given_an_urgent_unticked_mail_when_decided_then_the_urgency_label_is_used() -> None:
    decision = decide_alert(urgent=True, ticked=[])

    assert decision is not None
    assert decision.label == URGENT_LABEL == "Urgent: needs your attention"
    assert decision.causes == (AlertCause(CauseKind.URGENT),)


def test_given_an_urgent_mail_in_two_ticked_categories_when_decided_then_one_decision_names_every_cause() -> None:
    decision = decide_alert(urgent=True, ticked=["A", "B"])

    assert decision is not None
    assert decision.causes == (
        AlertCause(CauseKind.URGENT),
        AlertCause(CauseKind.ALWAYS_NOTIFY, "A"),
        AlertCause(CauseKind.ALWAYS_NOTIFY, "B"),
    )
    assert decision.label == URGENT_LABEL
    assert [cause.describe() for cause in decision.causes[1:]] == ["Always notify: A", "Always notify: B"]


def test_given_the_same_category_twice_when_decided_then_it_is_named_once() -> None:
    decision = decide_alert(urgent=False, ticked=["A", "A"])

    assert decision is not None
    assert decision.causes == (AlertCause(CauseKind.ALWAYS_NOTIFY, "A"),)


def test_given_causes_when_encoded_and_decoded_then_they_round_trip_and_garbage_is_dropped() -> None:
    causes = (AlertCause(CauseKind.URGENT), AlertCause(CauseKind.ALWAYS_NOTIFY, "Huis/Energie"))

    assert decode_causes(encode_causes(causes)) == causes
    assert decode_causes(["urgent", "weird", "always_notify:", 7]) == (AlertCause(CauseKind.URGENT),)  # type: ignore[list-item]
    assert decode_causes(None) == (AlertCause(CauseKind.URGENT),)  # an alert written before causes existed
