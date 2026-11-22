"""Sender-rule filing: the authenticated From domain files a mail without a category call (ADR-0054, C-4, C-5, C-10).

The decision uses only the parsed From address and Gmail's own verdict on its domain (``authenticated_from_domain``).
The display name, ``Reply-To``, the subject and the body never reach this module. A listed sender that Gmail does not
vouch for is reported as skipped, so the caller lets the model judge the mail and records why. The matcher comes from
``category-policy`` and is built once per list version.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from app.core.authentication import authenticated_from_domain
from category_policy.senders import Hit, Match, SenderCategory, build_matcher

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.adapters.judge_anthropic import TrimmedMail
    from app.core.judgement import JudgingList, ListedCategory

__all__ = [
    "FilingSource",
    "RuleFiling",
    "RuleSkipped",
    "SenderRules",
    "SenderRulesCache",
    "UrgencyJudge",
    "UrgencyVerdict",
]


class FilingSource(StrEnum):
    """How a mail came to be filed: the value of ``filing.source``."""

    MODEL = "model"
    SENDER_RULE = "sender_rule"
    SENDER_RULE_NOT_APPLIED = "sender_rule_not_applied"  # listed, but the sender is not authenticated


@dataclass(frozen=True, slots=True)
class UrgencyVerdict:
    """The answer of the urgency-only call: a boolean and a one-line reason, never a category."""

    needs_attention: bool
    reason: str


class UrgencyJudge(Protocol):
    """The small urgency-only model call for a mail a sender rule has filed in an unticked category (D11)."""

    async def needs_attention(self, mail: TrimmedMail) -> UrgencyVerdict:
        """Whether this one mail needs Marco's attention now."""
        ...


@dataclass(frozen=True, slots=True)
class RuleFiling:
    """A sender rule filed the mail: its topic, its extra label when one lists the sender, and the matched entry."""

    topic: ListedCategory
    extra: ListedCategory | None
    entry: str

    @property
    def ticked(self) -> bool:
        """Whether a matched category is set to always notify, so no urgency call is needed."""
        return self.topic.notify or (self.extra is not None and self.extra.notify)


@dataclass(frozen=True, slots=True)
class RuleSkipped:
    """The From matches a listed entry but Gmail does not vouch for the sender: no rule applies."""

    entry: str


class SenderRules:
    """The sender rules of one list version."""

    def __init__(self, categories: Sequence[ListedCategory]) -> None:
        """Build the matcher for these categories."""
        self._by_name = {category.name: category for category in categories}
        self._matcher = build_matcher([SenderCategory(c.name, c.kind, c.senders) for c in categories])

    def apply(self, auth_results: Sequence[str], sender: str) -> RuleFiling | RuleSkipped | None:
        """The rule for a mail, or ``None`` when the list does not file it.

        Args:
            auth_results: Every ``Authentication-Results`` value of the mail, topmost first.
            sender: The parsed From address (never the display name).

        Returns:
            ``RuleFiling`` for an authenticated sender a topic lists; ``RuleSkipped`` for a listed sender that is not
            authenticated; ``None`` otherwise (a sender only an extra label lists leaves the topic to the model).
        """
        headers = tuple(("Authentication-Results", value) for value in auth_results)
        domain = authenticated_from_domain(headers, sender)
        if domain is None:
            return _skipped(self._matcher(sender))
        local = sender.rpartition("@")[0]
        return self._filing(self._matcher(f"{local}@{domain}"))  # the vouched domain, nothing else

    def _filing(self, found: Match | None) -> RuleFiling | None:
        if found is None or found.topic is None:
            return None
        extra = self._by_name[found.extra.category] if found.extra else None
        return RuleFiling(self._by_name[found.topic.category], extra, found.topic.entry)


def _skipped(found: Match | None) -> RuleSkipped | None:
    hit: Hit | None = found and (found.topic or found.extra)
    return None if hit is None else RuleSkipped(hit.entry)


class SenderRulesCache:
    """Keeps the rules of the latest list version, so the matcher is built once per version."""

    def __init__(self) -> None:
        """Start empty."""
        self._version: int | None = None
        self._rules: SenderRules | None = None

    def for_list(self, current: JudgingList) -> SenderRules:
        """The rules of ``current``; built again only when the version changed."""
        if self._rules is None or self._version != current.version:
            self._rules = SenderRules(current.categories)
            self._version = current.version
        return self._rules
