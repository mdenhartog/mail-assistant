"""Name, description and list rules for categories (INT-004, C-3, AC-2, AC-8).

Everything here is pure and total: validation reports problems, it never raises on any text.
"""

import unicodedata
from collections.abc import Collection, Sequence
from dataclasses import dataclass

NAME_MAX = 40
DESCRIPTION_MAX = 500
MAX_CATEGORIES = 50
LABEL_PREFIX = "Assistant/"
RESERVED_NAMES = frozenset({"other", "archive"})
DECISIONS = ("pending", "approved", "rejected")

RULES = (
    "name_empty",
    "name_too_long",
    "name_slash",
    "name_forbidden_char",
    "name_reserved",
    "name_duplicate",
    "name_label_exists",
    "description_empty",
    "description_too_long",
    "list_too_many",
)

_FORBIDDEN_CATEGORIES = frozenset({"Cc", "Cf"})


@dataclass(frozen=True, slots=True)
class Category:
    """A category as the user writes it."""

    name: str
    description: str


@dataclass(frozen=True, slots=True)
class Problem:
    """One refusal.

    Attributes:
        rule: Stable rule id, one of ``RULES``.
        field: ``name``, ``description`` or ``list``.
        index: Position of the category in the list, or None for a single category or a rule about the whole list.
    """

    rule: str
    field: str
    index: int | None = None


def _canonical(raw: str) -> str:
    """Trim and apply NFKC, keeping the letter case (what is stored and measured)."""
    return unicodedata.normalize("NFKC", raw.strip()).strip()


def normalise_name(raw: str) -> str:
    """Return the comparison key of a name: trim, NFKC, case folding.

    Look-alikes (full-width letters, ligatures) and letter case variants give the same key. The result is
    stable: normalising it again changes nothing.

    Args:
        raw: The name as typed.

    Returns:
        The normalised name.
    """
    folded = unicodedata.normalize("NFKC", _canonical(raw).casefold())
    return folded.casefold().strip()


def label_for(name: str) -> str:
    """Return the Gmail label of a category: ``Assistant/<name>`` with the trimmed name.

    Args:
        name: The category name.

    Returns:
        The label name.
    """
    return f"{LABEL_PREFIX}{name.strip()}"


def _name_problems(
    name: str, existing: Collection[str], labels: Collection[str], adoptable: Collection[str]
) -> list[Problem]:
    canonical = _canonical(name)
    if not canonical:
        return [Problem("name_empty", "name")]
    rules: list[str] = []
    if len(canonical) > NAME_MAX:
        rules.append("name_too_long")
    if "/" in canonical:
        rules.append("name_slash")
    if ".." in canonical or any(unicodedata.category(char) in _FORBIDDEN_CATEGORIES for char in canonical):
        rules.append("name_forbidden_char")
    key = normalise_name(name)
    if key in RESERVED_NAMES:
        rules.append("name_reserved")
    if key in {normalise_name(other) for other in existing}:
        rules.append("name_duplicate")
    else:
        label_key = normalise_name(label_for(canonical))
        if label_key in {normalise_name(label) for label in labels} - {normalise_name(label) for label in adoptable}:
            rules.append("name_label_exists")
    return [Problem(rule, "name") for rule in rules]


def _description_problems(description: str) -> list[Problem]:
    trimmed = description.strip()
    if not trimmed:
        return [Problem("description_empty", "description")]
    if len(trimmed) > DESCRIPTION_MAX:
        return [Problem("description_too_long", "description")]
    return []


def validate_category(
    name: str,
    description: str,
    existing: Collection[str],
    labels: Collection[str],
    adoptable: Collection[str],
) -> list[Problem]:
    """Check one category against the name and description rules.

    Args:
        name: The proposed name.
        description: The proposed description.
        existing: Names of the other categories on the list (compared after normalisation).
        labels: The Gmail labels that exist, as the caller knows them.
        adoptable: The subset of ``labels`` that belongs to an older category (an ``Assistant/`` label that is not
            on the stored list and whose suffix is not reserved). A new category of that name adopts the label
            and its mail instead of clashing (C-15, AC-40, AC-53). Compared after the same normalisation as names.

    Returns:
        The problems in rule order; empty when the category is valid.
    """
    return [*_name_problems(name, existing, labels, adoptable), *_description_problems(description)]


def validate_list(categories: Sequence[Category], labels: Collection[str], adoptable: Collection[str]) -> list[Problem]:
    """Check a whole list: every category (a later duplicate is the one flagged) and the cap.

    Args:
        categories: The list in order.
        labels: The Gmail labels that exist, as the caller knows them.
        adoptable: The subset of ``labels`` that belongs to an older category and may be adopted.

    Returns:
        The problems with the index of their category; empty when the list is valid.
    """
    problems: list[Problem] = []
    for index, category in enumerate(categories):
        earlier = [other.name for other in categories[:index]]
        problems.extend(
            Problem(problem.rule, problem.field, index)
            for problem in validate_category(category.name, category.description, earlier, labels, adoptable)
        )
    if len(categories) > MAX_CATEGORIES:
        problems.append(Problem("list_too_many", "list"))
    return problems
