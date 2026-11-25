"""Seed factories: plan-sized data sets, look-alike names, bidi subjects and canary strings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.fakes.fake_gmail import FakeGmail

PLAN_ITEMS = 1000
PLAN_GROUPS = 20
SCOPE_MAILS = 5001

# Strings that must never appear in logs, Sentry events or Telegram notices.
CANARIES: tuple[str, ...] = ("test-canary-sender-7f3a", "test-canary-subject-c91d", "test-canary-body-52be")

# Right-to-left and isolate controls that can reorder displayed text. Built with chr() so no source line carries them.
RLO, LRO, PDF, LRI, RLI, PDI = (chr(c) for c in (0x202E, 0x202D, 0x202C, 0x2066, 0x2067, 0x2069))
BIDI_CONTROLS: tuple[str, ...] = (RLO, LRO, LRI, RLI, PDI)


@dataclass(frozen=True, slots=True)
class PlanItem:
    """One plan-like row: a mail that would move from one category to another."""

    item_id: str
    mail_id: str
    group: str
    from_category: str
    to_category: str


@dataclass(frozen=True, slots=True)
class Category:
    """One category of the user's list."""

    category_id: str
    name: str


def plan_items(count: int = PLAN_ITEMS, groups: int = PLAN_GROUPS) -> list[PlanItem]:
    """``count`` items spread evenly over ``groups`` (from, to) groups."""
    return [
        PlanItem(
            item_id=f"item-{n:05d}",
            mail_id=f"mail-{n:05d}",
            group=f"group-{n % groups:02d}",
            from_category=f"From {n % groups:02d}",
            to_category=f"To {n % groups:02d}",
        )
        for n in range(count)
    ]


def categories(count: int) -> list[Category]:
    """``count`` categories with unique names (50 is the limit, 51 must be refused)."""
    return [Category(category_id=f"cat-{n}", name=f"Category {n:02d}") for n in range(1, count + 1)]


def seed_scope_mails(gmail: FakeGmail, count: int = SCOPE_MAILS) -> list[str]:
    """Put ``count`` in-scope (inbox, not spam or trash) mails in the fake mailbox; return their ids."""
    return [gmail.add_mail(subject=f"test-subject-{n}") for n in range(count)]


def _fullwidth(text: str) -> str:
    """ASCII letters and digits as their fullwidth forms, which NFKC folds back."""
    return "".join(chr(ord(c) + 0xFEE0) if c.isascii() and c.isalnum() else c for c in text)


def lookalike_names() -> list[tuple[str, str]]:
    """Pairs ``(plain, look-alike)``: different strings that NFKC-normalise to the same name."""
    return [
        ("Bills", _fullwidth("B") + "ills"),
        ("finance", chr(0xFB01) + "nance"),  # fi ligature
        ("Archive", "Arc" + _fullwidth("h") + "ive"),
        ("Travel2", "Travel" + _fullwidth("2")),
    ]


def bidi_subjects() -> list[str]:
    """Subjects with bidi controls that could disguise text or reorder it on screen."""
    return [
        f"Invoice {RLO}gnp.exe",
        f"{LRI}Hello{PDI} world",
        f"Re: {LRO}payment{PDF} due",
        f"{RLI}Meeting{PDI}",
    ]
