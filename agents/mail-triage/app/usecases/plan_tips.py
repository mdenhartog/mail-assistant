"""Tips for a ``review`` plan that just became ready (ADR-0056 decision 6, spec C-15, AC-52, AC-58).

One model call per category that has items below the threshold, none for the others. The call gets the category, its
description and the sender domain and subject of those items, never a body. The answer is cleaned and its sender checked
by ``app.core.tips`` and the result is stored on the plan items of that category. A tip is only text on the plan items:
nothing here changes the list, a label or Gmail, and the items take the tip with them when they go (it is a column).

A tip is a help, not part of the plan: when the budget is at the reserve or the model is down, the plan stays as it is
and the categories simply have no tip.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.adapters.judge_anthropic import ModelUnavailable
from app.adapters.tip_anthropic import TipAnswer, TipItem, TipNotMade
from app.core.tips import compose_tip, qualified_domains

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from app.core.judgement import ListedCategory

__all__ = ["PlanTips", "TipModel", "TipRow", "TipStore"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TipRow:
    """What a below-threshold item contributes: its new topic, its sender domain, subject and verified domain."""

    category_id: str
    sender_domain: str
    subject: str
    verified_domain: str | None  # the From domain Gmail vouched for when the mail was filed; ``None`` when unknown


class TipStore(Protocol):
    """The plan items of a ``review`` plan."""

    async def below_threshold(self, plan_id: uuid.UUID) -> list[TipRow]:
        """The items of the ``review`` plan, which are all below its threshold."""
        ...

    async def store_tip(self, plan_id: uuid.UUID, category_id: str, tip: str) -> None:
        """Write the tip on the items of that category in that plan."""
        ...


class TipModel(Protocol):
    """The model call."""

    async def tip(self, name: str, description: str, items: Sequence[TipItem]) -> TipAnswer | TipNotMade:
        """One tip answer for one category, or why there is none."""
        ...


class PlanTips:
    """Writes the tips of a ready ``review`` plan."""

    def __init__(self, *, model: TipModel, store: TipStore) -> None:
        """Wire the model call and the plan items."""
        self._model = model
        self._store = store

    async def write(self, plan_id: uuid.UUID, categories: Sequence[ListedCategory]) -> int:
        """Store a tip per category with items below the threshold; return how many were stored."""
        rows = await self._store.below_threshold(plan_id)
        by_category: dict[str, list[TipRow]] = {}
        for row in rows:
            by_category.setdefault(row.category_id, []).append(row)
        listed = {category.category_id: category for category in categories}
        stored = 0
        for category_id, group in sorted(by_category.items(), key=lambda pair: -len(pair[1])):
            category = listed.get(category_id)
            if category is None:  # "Other" or a category the list no longer has: no category to give a tip for
                continue
            try:
                answer = await self._model.tip(
                    category.name, category.description, [TipItem(r.sender_domain, r.subject) for r in group]
                )
            except ModelUnavailable:
                logger.warning("model unavailable; the plan has no more tips")
                break
            if isinstance(answer, TipNotMade):
                if answer.reason == "budget":
                    logger.info("tip budget used up; the plan has no more tips")
                    break
                continue
            tip = compose_tip(answer.text, answer.sender, qualified_domains(r.verified_domain for r in group))
            if tip is not None:
                await self._store.store_tip(plan_id, category_id, tip)
                stored += 1
        return stored
