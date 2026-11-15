"""Seeding helpers for the plan tests (U-mail-categories-12): the owner writes plans and items like the agent."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg

NIL = uuid.UUID(int=0)  # the built-in "Other"
CAT_A = uuid.UUID(int=1)
CAT_B = uuid.UUID(int=2)
CAT_C = uuid.UUID(int=3)
Move = tuple[uuid.UUID, uuid.UUID]  # old category, new category
DEFAULT_MOVES: tuple[Move, ...] = ((NIL, CAT_A), (NIL, CAT_A), (NIL, CAT_B), (CAT_A, CAT_B), (CAT_B, CAT_C))


@dataclass(frozen=True)
class SeededPlan:
    """A plan and its items as the tests need to name them."""

    mailbox: str
    plan_id: uuid.UUID
    item_ids: list[int]
    message_ids: list[str]


async def seed_plan(  # noqa: PLR0913
    owner: asyncpg.Connection,
    mailbox: str = "mb1",
    *,
    state: str = "ready",
    moves: tuple[Move, ...] = DEFAULT_MOVES,
    list_version: int = 1,
    tag: str = "m",
) -> SeededPlan:
    """Insert a plan in ``state`` with one item per move; ``tag`` keeps message ids apart between plans."""
    plan_id = uuid.uuid4()
    await owner.execute(
        "insert into categories.plan (mailbox_id, id, list_version, state) values ($1, $2, $3, $4)",
        mailbox,
        plan_id,
        list_version,
        state,
    )
    item_ids: list[int] = []
    message_ids: list[str] = []
    for index, (old, new) in enumerate(moves):
        message_id = f"{tag}{index}"
        item_id = await owner.fetchval(
            "insert into categories.plan_item "
            "(mailbox_id, plan_id, message_id, sender_name, sender_address, subject, old_category_id, new_category_id) "
            "values ($1, $2, $3, 'Sender Name', 'sender@example.test', 'A subject', $4, $5) returning id",
            mailbox,
            plan_id,
            message_id,
            old,
            new,
        )
        item_ids.append(int(str(item_id)))
        message_ids.append(message_id)
    return SeededPlan(mailbox, plan_id, item_ids, message_ids)


async def set_apply_config(
    owner: asyncpg.Connection, mailbox: str = "mb1", *, threshold: int = 50, delay_minutes: int = 15
) -> None:
    """The one row the approval function reads (the agent writes it from its deployment configuration)."""
    await owner.execute(
        "insert into categories.apply_config (mailbox_id, threshold, delay_minutes) values ($1, $2, $3) "
        "on conflict (mailbox_id) do update set threshold = excluded.threshold, delay_minutes = excluded.delay_minutes",
        mailbox,
        threshold,
        delay_minutes,
    )


def scope_all() -> str:
    """The ``all`` shape of the decision scope, as the JSON text the function takes."""
    return json.dumps({"kind": "all"})


def scope_ids(ids: list[int]) -> str:
    """The ``ids`` shape."""
    return json.dumps({"kind": "ids", "ids": ids})


def scope_group(old: uuid.UUID, new: uuid.UUID, count: int) -> str:
    """The ``group`` shape: the items that move from ``old`` to ``new`` and how many the caller saw."""
    return json.dumps({"kind": "group", "from": str(old), "to": str(new), "groupCount": count})
