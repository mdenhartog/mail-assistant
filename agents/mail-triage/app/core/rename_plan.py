"""The one-off rename plan: which labels of the old form become which names (spec D8, D9; ADR-0060, ADR-0061).

Pure logic. Every Gmail label under the old prefix is a candidate, including those of categories that left the list
(D9). The new name is the old name without the prefix. When a label of that name exists already (letter case does not
count: Gmail names are unique ignoring case) the plan item is a *merge* (D8), otherwise a *rename*.

A label is left out of the plan, and so never touched, when it is not under the prefix, when the root label (the bare
prefix word) has no name left to give, when the new name would be empty or would still start with the prefix, or when
the new name is that of a Gmail system label (mail is never merged onto one). The prefix is built from two parts on
purpose: the old form of a name appears in the source in this module's rule and in the sync's gate only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.core.managed import LabelRef

__all__ = ["LEGACY_PREFIX", "PlanItem", "build_plan"]

LEGACY_PREFIX = "assistant" + "/"  # the label prefix of the releases before INT-010, compared in lower case


@dataclass(frozen=True, slots=True)
class PlanItem:
    """One label of the plan: its Gmail id, the name it has, the name it gets, the action and the mails on it."""

    label_id: str
    old_name: str
    new_name: str
    action: Literal["rename", "merge"]
    mail_count: int = 0


def _is_system(label: LabelRef) -> bool:
    """Gmail's own labels have their name as id (``INBOX``, ``CATEGORY_PERSONAL``); a user label has ``Label_n``."""
    return label.label_id == label.name


def build_plan(labels: Iterable[LabelRef]) -> list[PlanItem]:
    """The plan items for the labels of the mailbox, ordered by new name (letter case ignored)."""
    every = list(labels)
    by_name = {label.name.casefold(): label for label in every}
    items: list[PlanItem] = []
    for label in every:
        if _is_system(label) or not label.name.casefold().startswith(LEGACY_PREFIX):
            continue
        new_name = label.name[len(LEGACY_PREFIX) :]
        if not new_name or new_name.casefold().startswith(LEGACY_PREFIX):
            continue
        clash = by_name.get(new_name.casefold())
        if clash is not None and _is_system(clash):
            continue
        items.append(PlanItem(label.label_id, label.name, new_name, "merge" if clash is not None else "rename"))
    return sorted(items, key=lambda item: (item.new_name.casefold(), item.label_id))
