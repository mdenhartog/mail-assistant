"""U-mail-categories-05, criteria 1 to 3 (AC-5 to AC-8, AC-38; ADR-0045): judging against a closed set of ids."""

from __future__ import annotations

import uuid

import pytest

from app.core.judgement import (
    OTHER_ID,
    OTHER_LABEL,
    SUMMARY_MAX_CHARS,
    Filing,
    Judgement,
    ListedCategory,
    NeedsAttention,
    decide,
    parse_judgement,
    resolve,
)
from tests.fakes.stub_model import HOSTILE_CORPUS

LIST = tuple(
    ListedCategory(category_id=str(uuid.UUID(int=n)), name=f"Topic {n:02d}", description=f"About topic {n}")
    for n in range(1, 41)
)


def answer(category_id: str, **changes: object) -> dict[str, object]:
    return {
        "category_id": category_id,
        "urgent": False,
        "reason": "r",
        "summary": "s",
        "confidence": 0.9,
        **changes,
    }


def judgement(category_id: str, **changes: object) -> Judgement:
    return parse_judgement(answer(category_id, **changes))


def test_given_a_list_of_40_categories_when_judged_then_every_category_can_be_used() -> None:
    labels = []
    for category in LIST:
        result = resolve(judgement(category.category_id), LIST)

        assert isinstance(result, Filing)
        assert result.category_id == category.category_id
        labels.append(result.label)

    assert labels == [f"Assistant/Topic {n:02d}" for n in range(1, 41)]
    assert len(set(labels)) == 40


def test_given_an_id_of_the_list_when_resolved_then_the_mail_carries_exactly_that_one_label() -> None:
    result = resolve(judgement(LIST[6].category_id), LIST)

    assert isinstance(result, Filing)
    assert result.label == "Assistant/Topic 07"


def test_given_the_nil_id_when_resolved_then_it_is_other() -> None:
    result = resolve(judgement(OTHER_ID), LIST)

    assert isinstance(result, Filing)
    assert (result.label, result.category_id) == (OTHER_LABEL, OTHER_ID)


@pytest.mark.parametrize("hostile", [h for h in HOSTILE_CORPUS if h and len(h) <= 1000])
def test_given_a_hostile_answer_in_the_category_slot_when_resolved_then_the_mail_goes_to_other(hostile: str) -> None:
    result = resolve(judgement(hostile), LIST)

    assert isinstance(result, Filing)
    assert (result.label, result.category_id) == (OTHER_LABEL, OTHER_ID)


@pytest.mark.parametrize("hostile", ["", "x" * 1001])
def test_given_an_empty_or_overlong_answer_when_decided_then_it_needs_attention_and_files_under_other_later(
    hostile: str,
) -> None:
    assert decide(answer(hostile), LIST) == NeedsAttention("invalid_output")


def test_given_the_id_in_another_case_or_with_spaces_when_resolved_then_it_is_not_a_match() -> None:
    upper = LIST[9].category_id.upper()  # ends in "a", so upper-casing changes it
    padded = f" {LIST[0].category_id}"

    for given in (upper, padded):
        result = resolve(judgement(given), LIST)

        assert isinstance(result, Filing)
        assert result.category_id == OTHER_ID


def test_given_a_description_other_everything_when_an_urgent_mail_arrives_then_urgency_is_kept() -> None:
    everything = (ListedCategory(OTHER_ID, "Misc", "Other: everything, never urgent"), *LIST)

    result = resolve(judgement(LIST[2].category_id, urgent=True), everything)

    assert isinstance(result, Filing)
    assert result.judgement.urgent is True


@pytest.mark.parametrize("urgent", [True, False])
def test_given_an_unknown_id_when_resolved_then_it_goes_to_other_and_keeps_the_urgency(urgent: bool) -> None:  # noqa: FBT001
    result = resolve(judgement("cat-9999", urgent=urgent), LIST)

    assert isinstance(result, Filing)
    assert result.label == OTHER_LABEL
    assert result.judgement.urgent is urgent


def test_given_an_empty_list_when_resolved_then_every_mail_goes_to_other() -> None:
    result = resolve(judgement(LIST[0].category_id), ())

    assert isinstance(result, Filing)
    assert result.label == OTHER_LABEL


def test_given_low_confidence_when_resolved_then_it_is_needs_attention() -> None:
    assert resolve(judgement(LIST[0].category_id, confidence=0.3), LIST) == NeedsAttention("low_confidence")


@pytest.mark.parametrize(
    "raw",
    [
        {**answer("x"), "send_to": "attacker@example.com"},  # extra field
        {**answer("x"), "category": "Finance"},  # the old free name is no longer a field
        answer("x", urgent="yes"),  # wrong type
        answer("x", confidence="0.9"),
        answer("x", confidence=1.5),
        {k: v for k, v in answer("x").items() if k != "reason"},
        "ignore previous instructions",
        None,
    ],
)
def test_given_output_outside_the_schema_when_decided_then_it_is_needs_attention(raw: object) -> None:
    assert decide(raw, LIST) == NeedsAttention("invalid_output")


def test_given_text_longer_than_the_cap_when_parsed_then_it_is_cut() -> None:
    result = judgement("x", summary="s" * (SUMMARY_MAX_CHARS + 500), reason="r" * 5000)

    assert len(result.summary) == SUMMARY_MAX_CHARS
    assert len(result.reason) <= 200


def test_given_the_module_when_read_then_there_is_no_category_cap() -> None:
    import app.core.judgement as module  # noqa: PLC0415

    assert not hasattr(module, "MAX_CATEGORIES")
