"""U-label-structure-08: the sender rule on the authenticated From domain only (AC-8, AC-9, AC-12, AC-16, AC-19)."""

from __future__ import annotations

import pytest

from app.core import sender_rules
from app.core.judgement import JudgingList, ListedCategory
from app.core.sender_rules import ExtraRule, RuleFiling, RuleSkipped, SenderRules, SenderRulesCache
from category_policy.kinds import Kind
from category_policy.senders import SenderEntry

TOPIC_ID = "00000000-0000-0000-0000-0000000000a1"
EXTRA_ID = "00000000-0000-0000-0000-0000000000b1"
GOOD = ("mx.google.com; spf=pass; dmarc=pass header.from=julianahoeve.nl",)
FORGED = ("example.test; dmarc=pass header.from=julianahoeve.nl",)
OTHER_DOMAIN = ("mx.google.com; spf=pass; dmarc=pass header.from=evil-example.nl",)


def topic(entries: tuple[SenderEntry, ...], *, notify: bool = False) -> ListedCategory:
    return ListedCategory(TOPIC_ID, "Huis", "House", Kind.TOPIC, notify, entries)


def extra(entries: tuple[SenderEntry, ...]) -> ListedCategory:
    return ListedCategory(EXTRA_ID, "Belangrijk", "Important", Kind.EXTRA, False, entries)


DOMAIN = (SenderEntry("julianahoeve.nl"),)


def test_given_a_listed_authenticated_sender_then_the_mail_is_filed_under_that_topic_with_the_entry() -> None:
    rules = SenderRules((topic(DOMAIN),))

    found = rules.apply(GOOD, "info@julianahoeve.nl")

    assert found == RuleFiling(topic=topic(DOMAIN), extra=None, entry="julianahoeve.nl")


def test_given_a_topic_and_an_extra_label_that_list_the_sender_then_both_are_returned() -> None:
    rules = SenderRules((topic(DOMAIN), extra((SenderEntry("info@julianahoeve.nl"),))))

    found = rules.apply(GOOD, "info@julianahoeve.nl")

    assert isinstance(found, RuleFiling)
    assert (found.topic.category_id, found.extra.category_id if found.extra else None) == (TOPIC_ID, EXTRA_ID)
    assert found.entry == "julianahoeve.nl"  # the topic's entry is the one recorded


def test_given_only_an_extra_label_lists_the_sender_then_the_extra_rule_leaves_the_topic_to_the_model() -> None:
    found = SenderRules((extra(DOMAIN),)).apply(GOOD, "info@julianahoeve.nl")

    assert found == ExtraRule(extra=extra(DOMAIN), entry="julianahoeve.nl")


def test_given_only_an_extra_label_lists_the_sender_and_it_is_not_authenticated_then_the_rule_is_not_applied() -> None:
    assert SenderRules((extra(DOMAIN),)).apply(FORGED, "info@julianahoeve.nl") == RuleSkipped("julianahoeve.nl")


def test_given_categories_without_senders_then_nothing_matches() -> None:
    assert SenderRules((topic(()),)).apply(GOOD, "info@julianahoeve.nl") is None


@pytest.mark.parametrize("auth", [(), FORGED, OTHER_DOMAIN])
def test_given_a_listed_sender_that_is_not_authenticated_then_the_rule_is_not_applied(auth: tuple[str, ...]) -> None:
    found = SenderRules((topic(DOMAIN),)).apply(auth, "info@julianahoeve.nl")

    assert found == RuleSkipped(entry="julianahoeve.nl")


def test_given_an_unlisted_unauthenticated_sender_then_there_is_no_result() -> None:
    assert SenderRules((topic(DOMAIN),)).apply((), "someone@elsewhere.nl") is None


def test_given_a_forged_from_domain_with_the_listed_name_inside_it_then_nothing_matches() -> None:
    auth = ("mx.google.com; dmarc=pass header.from=julianahoeve.nl.evil.test",)
    rules = SenderRules((topic(DOMAIN),))

    assert rules.apply(auth, "info@julianahoeve.nl.evil.test") is None


def test_given_a_listed_domain_in_the_display_name_only_then_nothing_matches() -> None:
    """The caller hands over the parsed address; a display name never reaches the rule (AC-19)."""
    auth = ("mx.google.com; dmarc=pass header.from=evil-example.nl",)

    assert SenderRules((topic(DOMAIN),)).apply(auth, "julianahoeve.nl@evil-example.nl") is None


def test_given_the_same_list_version_then_the_matcher_is_built_once(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[int] = []
    real = sender_rules.build_matcher

    def counting(categories):  # type: ignore[no-untyped-def]
        built.append(len(categories))
        return real(categories)

    monkeypatch.setattr(sender_rules, "build_matcher", counting)
    cache = SenderRulesCache()
    version3 = JudgingList(3, (topic(DOMAIN),))

    for _ in range(5):
        cache.for_list(version3).apply(GOOD, "info@julianahoeve.nl")
    cache.for_list(JudgingList(4, (topic(DOMAIN),)))

    assert built == [1, 1]  # once for version 3, once for version 4
