"""Name, description, instruction and list rules for categories, version 2 (INT-008, C-1, C-3, C-6).

Everything here is pure and total: validation reports problems, it never raises on any text.
A name is a path of segments joined by ``/`` (``Huis/Energie``); the rules of INT-004 apply per segment.
"""

import math
import unicodedata
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from category_policy.kinds import Kind

SEGMENT_MAX = 40
# Longest label name in Unicode characters (code points) of the stored form, slashes included; bytes do not count.
LABEL_MAX = 255
DESCRIPTION_MAX = 1500
INSTRUCTIONS_MAX = 4000
MAX_CATEGORIES = 100
SEPARATOR = "/"
OTHER_LABEL_DEFAULT = "Other"
ARCHIVE_LABEL_DEFAULT = "Archive"
# One list of reserved names for list categories and setting names alike (ADR-0060): a first segment Other or
# Archive, the Gmail system labels below (whole name, any letter case) and the legacy prefix ``Assistant/``. A setting
# may still equal its own default. All comparisons run on ``normalise_name`` (NFKC, case folding).
RESERVED_NAMES = frozenset({"other", "archive"})
GMAIL_SYSTEM_LABELS = frozenset(
    {
        "inbox",
        "spam",
        "trash",
        "sent",
        "sent mail",
        "draft",
        "drafts",
        "all mail",
        "starred",
        "unread",
        "important",
        "chat",
        "chats",
        "snoozed",
    }
)
GMAIL_SYSTEM_LABEL_PREFIX = "category_"
LEGACY_PREFIX = "assistant/"
DECISIONS = ("pending", "approved", "rejected")

RULES = (
    "name_empty",
    "name_segment_empty",
    "name_segment_too_long",
    "name_label_too_long",
    "name_forbidden_char",
    "name_reserved",
    "name_duplicate",
    "name_setting_clash",
    "description_empty",
    "description_too_long",
    "instructions_too_long",
    "list_too_many",
)

SETTING_NAME_RULES = (
    "setting_name_invalid",
    "setting_name_too_long",
    "setting_name_system_label",
    "setting_name_reserved",
    "setting_name_category_clash",
)

_FORBIDDEN_CATEGORIES = frozenset({"Cc", "Cf"})
# Look-alikes of "/" that NFKC leaves alone (U+FF0F is folded by NFKC; U+2215 is not). Both fold before the rules run.
_SLASH_LOOK_ALIKE_CHARS = (chr(0x2215), chr(0xFF0F))  # DIVISION SLASH, FULLWIDTH SOLIDUS
_SLASH_LOOK_ALIKES = str.maketrans(dict.fromkeys(_SLASH_LOOK_ALIKE_CHARS, SEPARATOR))


@dataclass(frozen=True, slots=True)
class Category:
    """A category as the user writes it."""

    name: str
    description: str
    kind: Kind = Kind.TOPIC


@dataclass(frozen=True, slots=True)
class Problem:
    """One refusal.

    Attributes:
        rule: Stable rule id, one of ``RULES``.
        field: ``name``, ``description``, ``instructions`` or ``list``.
        index: Position of the category in the list, or None for a single category or a rule about the whole list.
    """

    rule: str
    field: str
    index: int | None = None


def _segments(raw: str) -> list[str]:
    """Fold look-alikes of ``/`` and NFKC, then split into trimmed segments (letter case kept)."""
    folded = unicodedata.normalize("NFKC", raw.translate(_SLASH_LOOK_ALIKES)).translate(_SLASH_LOOK_ALIKES)
    return [segment.strip() for segment in folded.strip().split(SEPARATOR)]


def _canonical(raw: str) -> str:
    """Return the stored form of a name: look-alikes folded, NFKC, every segment trimmed."""
    return SEPARATOR.join(_segments(raw))


def normalise_name(raw: str) -> str:
    """Return the comparison key of a name: look-alikes of ``/`` folded, trim per segment, NFKC, case folding.

    Look-alikes (full-width letters, ligatures, other slashes) and letter case variants give the same key. The
    result is stable: normalising it again changes nothing.

    Args:
        raw: The name as typed.

    Returns:
        The normalised name.
    """
    folded = unicodedata.normalize("NFKC", _canonical(raw).casefold())
    return _canonical(folded.casefold())


def label_for(name: str) -> str:
    """Return the Gmail label of a category: the canonical list name, without any prefix (ADR-0060).

    Args:
        name: The category name, nested with ``/``.

    Returns:
        The label name.
    """
    return _canonical(name)


def _is_system_label(key: str) -> bool:
    return key in GMAIL_SYSTEM_LABELS or key.startswith(GMAIL_SYSTEM_LABEL_PREFIX)


def _is_legacy_prefixed(key: str) -> bool:
    """Whether a comparison key starts with the retired ``Assistant/`` prefix."""
    return key.startswith(LEGACY_PREFIX)


def _name_rules(canonical: str, segments: list[str]) -> list[str]:
    rules: list[str] = []
    if not all(segments):
        rules.append("name_segment_empty")
    if any(len(segment) > SEGMENT_MAX for segment in segments):
        rules.append("name_segment_too_long")
    if len(canonical) > LABEL_MAX:
        rules.append("name_label_too_long")
    if ".." in canonical or any(unicodedata.category(char) in _FORBIDDEN_CATEGORIES for char in canonical):
        rules.append("name_forbidden_char")
    key = normalise_name(canonical)
    if normalise_name(segments[0]) in RESERVED_NAMES or _is_system_label(key) or _is_legacy_prefixed(key):
        rules.append("name_reserved")
    return rules


def _name_problems(name: str, existing: Collection[str], settings: Collection[str]) -> list[Problem]:
    segments = _segments(name)
    canonical = SEPARATOR.join(segments)
    if not canonical:
        return [Problem("name_empty", "name")]
    rules = _name_rules(canonical, segments)
    key = normalise_name(name)
    if key in {normalise_name(other) for other in existing}:
        rules.append("name_duplicate")
    elif "name_reserved" not in rules and key in {normalise_name(setting) for setting in settings}:
        rules.append("name_setting_clash")
    return [Problem(rule, "name") for rule in rules]


def _description_problems(description: str) -> list[Problem]:
    trimmed = description.strip()
    if not trimmed:
        return [Problem("description_empty", "description")]
    if len(trimmed) > DESCRIPTION_MAX:
        return [Problem("description_too_long", "description")]
    return []


def validate_instructions(instructions: str) -> list[Problem]:
    """Check the general instructions of a list: 0 to 4 000 characters after trimming.

    Args:
        instructions: The general instructions as typed.

    Returns:
        The problems; empty when the text is valid.
    """
    if len(instructions.strip()) > INSTRUCTIONS_MAX:
        return [Problem("instructions_too_long", "instructions")]
    return []


def confidence_pct(confidence: float) -> int:
    """Convert the model's confidence (0 to 1) to whole percent, rounding half up (ADR-0053 decision 4).

    The decimal text of the float is rounded, so ``0.295`` gives 30, not the 29 that binary arithmetic would.

    Args:
        confidence: The model's confidence from 0 to 1.

    Returns:
        The percentage from 0 to 100.

    Raises:
        ValueError: If the confidence is not a number from 0 to 1.
    """
    if math.isnan(confidence) or not 0.0 <= confidence <= 1.0:
        msg = f"confidence must be a number from 0 to 1, got {confidence!r}"
        raise ValueError(msg)
    return int((Decimal(repr(confidence)) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def at_or_above(confidence_percent: int, threshold: int) -> bool:
    """Compare a whole-percent confidence with a threshold in whole percent: at or above counts.

    Args:
        confidence_percent: The value from ``confidence_pct``.
        threshold: The plan threshold in whole percent.

    Returns:
        True when the confidence reaches the threshold.
    """
    return confidence_percent >= threshold


def _setting_name_invalid(name: str) -> bool:
    """Whether a setting name is malformed: empty, padded, ``..``, empty segment, control character or look-alike."""
    return (
        not name
        or ".." in name
        or any(unicodedata.category(char) in _FORBIDDEN_CATEGORIES for char in name)
        or any(char in name for char in _SLASH_LOOK_ALIKE_CHARS)
        or any(segment != segment.strip() or not segment for segment in name.split(SEPARATOR))
    )


def validate_label_setting_name(
    name: str, categories: Sequence[Category], counterpart: str, own_default: str
) -> list[Problem]:
    """Check the name of the "Other" label or of the archive label (ADR-0060, AC 13 and 32).

    A valid name has 1 to ``LABEL_MAX`` (255) Unicode characters (code points, not bytes; slashes count), no control
    or format characters, no ``..``, no look-alike of ``/``, no space around a segment and no empty segment (so no
    leading, trailing or double slash). It is not a Gmail system label (any letter case; ``CATEGORY_*`` too), not a
    reserved name (``Other``, ``Archive`` or a first segment of either: the one list that list categories use too)
    unless it is exactly the default of the setting being checked, not the name of the other setting, and not equal
    to or below the name of a list category (any letter case). Exactly one problem is reported, the most specific.

    Args:
        name: The proposed name, as typed (it is not trimmed).
        categories: The categories of the list.
        counterpart: The current name of the other setting, so the two cannot be the same label.
        own_default: The default name of the setting being checked (``Other`` or ``Archive``); the only reserved
            name that setting may take.

    Returns:
        The problems, all with field ``setting_name``; empty when the name is valid.
    """
    if _setting_name_invalid(name):
        return [Problem("setting_name_invalid", "setting_name")]
    if len(name) > LABEL_MAX:
        return [Problem("setting_name_too_long", "setting_name")]
    key = normalise_name(name)
    if _is_system_label(key):
        return [Problem("setting_name_system_label", "setting_name")]
    reserved = normalise_name(_segments(name)[0]) in RESERVED_NAMES and key != normalise_name(own_default)
    if reserved or _is_legacy_prefixed(key) or key == normalise_name(counterpart):
        return [Problem("setting_name_reserved", "setting_name")]
    for category in categories:
        category_key = normalise_name(label_for(category.name))
        if key == category_key or key.startswith(f"{category_key}{SEPARATOR}"):
            return [Problem("setting_name_category_clash", "setting_name")]
    return []


def validate_category(
    name: str, description: str, existing: Collection[str], settings: Collection[str]
) -> list[Problem]:
    """Check one category against the name and description rules.

    A label that exists already never refuses a name: the caller adopts it (ADR-0060); the package does not read Gmail.

    Args:
        name: The proposed name, nested with ``/``.
        description: The proposed description.
        existing: Names of the other categories on the list (compared after normalisation).
        settings: The current names of the "Other" label and the archive label; a category of that name clashes.

    Returns:
        The problems in rule order; empty when the category is valid.
    """
    return [*_name_problems(name, existing, settings), *_description_problems(description)]


def validate_list(categories: Sequence[Category], settings: Collection[str]) -> list[Problem]:
    """Check a whole list: every category (a later duplicate is the one flagged) and the cap.

    Args:
        categories: The list in order.
        settings: The current names of the "Other" label and the archive label.

    Returns:
        The problems with the index of their category; empty when the list is valid.
    """
    problems: list[Problem] = []
    for index, category in enumerate(categories):
        earlier = [other.name for other in categories[:index]]
        problems.extend(
            Problem(problem.rule, problem.field, index)
            for problem in validate_category(category.name, category.description, earlier, settings)
        )
    if len(categories) > MAX_CATEGORIES:
        problems.append(Problem("list_too_many", "list"))
    return problems
