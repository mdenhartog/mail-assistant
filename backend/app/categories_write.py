"""The glue between the category list API and the shared rules of ``category_policy`` (v2, U-label-structure-11).

Pure functions: no database, no clock, no randomness (the ids of new categories come from the id source).
"""

import uuid
from collections.abc import Callable

from app.categories_models import (
    CategoryInput,
    CategoryItem,
    CategoryList,
    CategoryProblem,
    OlderCategory,
    OtherItem,
    SenderItem,
    SenderView,
)
from app.categories_repo import OTHER_ID, StoredCategory, StoredList, StoredSender
from category_policy import (
    LABEL_PREFIX,
    Category,
    SenderCategory,
    SenderEntry,
    label_for,
    normalise_name,
    parse_entry,
    validate_archive_label,
    validate_entries,
    validate_instructions,
    validate_list,
)
from category_policy.policy import RESERVED_NAMES


def canonical_text(raw: str) -> str:
    """Return the stored form of a name: look-alikes folded, NFKC, every segment trimmed (the form the rules measure).

    Args:
        raw: The name as typed.

    Returns:
        The stored form of a name.
    """
    return label_for(raw).removeprefix(LABEL_PREFIX)


def older_labels(stored: StoredList) -> list[str]:
    """Return the ``Assistant/`` labels in Gmail that are not on the list (and are not a reserved name).

    Args:
        stored: The stored list with the label names the agent saw.

    Returns:
        The label names as Gmail has them.
    """
    on_list = {normalise_name(label_for(category.name)) for category in stored.categories}
    return [
        label
        for label in stored.labels
        if label.startswith(LABEL_PREFIX)
        and normalise_name(label) not in on_list
        and normalise_name(label.removeprefix(LABEL_PREFIX)) not in RESERVED_NAMES
    ]


def _labels_in_use(items: list[CategoryInput], stored: StoredList) -> set[str]:
    """Return the normalised labels of stored categories that the request keeps under the same name.

    A kept category owns its label; it is no clash with itself.
    """
    kept = {item.id: normalise_name(item.name) for item in items if item.id is not None}
    return {
        normalise_name(label_for(category.name))
        for category in stored.categories
        if kept.get(category.id) == normalise_name(category.name)
    }


def to_response(stored: StoredList) -> CategoryList:
    """Build what ``GET /api/categories`` returns.

    Args:
        stored: The stored list with its counts and labels.

    Returns:
        The list with the counts, "Other" and the older categories; ``ready`` once version 1 exists.
    """
    return CategoryList(
        version=stored.version,
        ready=stored.version >= 1,
        categories=[
            CategoryItem(
                id=category.id,
                name=category.name,
                description=category.description,
                kind=category.kind,
                notify=category.notify,
                senders=[
                    SenderView(
                        entry=sender.entry,
                        subdomains=sender.subdomains,
                        skipped_count=stored.skipped.get(sender.entry, 0),
                    )
                    for sender in category.senders
                ],
                mail_count=stored.counts.get(category.id, 0),
            )
            for category in stored.categories
        ],
        general_instructions=stored.general_instructions,
        archive_label=stored.archive_label,
        other=OtherItem(mail_count=stored.counts.get(OTHER_ID, 0)),
        older_categories=[OlderCategory(label_name=label, mail_count=None) for label in older_labels(stored)],
    )


def _sender_problems(items: list[CategoryInput]) -> list[CategoryProblem]:
    categories = [
        SenderCategory(
            item.name,
            item.kind,
            tuple(SenderEntry(sender.entry, sender.subdomains) for sender in item.senders),
        )
        for item in items
    ]
    return [
        CategoryProblem(
            rule=problem.rule,
            field="senders",
            index=problem.index,
            position=problem.position,
            other_index=problem.other_index,
        )
        for problem in validate_entries(categories)
    ]


def problems_of(
    items: list[CategoryInput], instructions: str, archive_label: str, stored: StoredList
) -> list[CategoryProblem]:
    """Check a whole list against the shared rules and the ids of the stored list.

    Args:
        items: The categories as sent.
        instructions: The general instructions as sent.
        archive_label: The archive label name as sent (ADR-0059).
        stored: The stored list: the known ids and the Gmail labels. A name whose label is an older category adopts it;
            a kept category's own label is no clash.

    Returns:
        Every problem with the rule, the field and the position; no value. Empty when the list is valid.
    """
    found = _list_problems(items, instructions, stored)
    found.extend(_sender_problems(items))
    found.extend(
        CategoryProblem(rule=problem.rule, field="archive_label", index=None, position=None, other_index=None)
        for problem in validate_archive_label(
            archive_label, [Category(item.name, item.description, item.kind) for item in items]
        )
    )
    found.extend(_id_problems(items, stored))
    return found


def _list_problems(items: list[CategoryInput], instructions: str, stored: StoredList) -> list[CategoryProblem]:
    own = _labels_in_use(items, stored)
    existing = [label for label in stored.labels if normalise_name(label) not in own]
    return [
        CategoryProblem(
            rule=problem.rule,
            field=problem.field,  # pyright: ignore[reportArgumentType]
            index=problem.index,
            position=None,
            other_index=None,
        )
        for problem in [
            *validate_list(
                [Category(item.name, item.description, item.kind) for item in items], existing, older_labels(stored)
            ),
            *validate_instructions(instructions),
        ]
    ]


def _id_problems(items: list[CategoryInput], stored: StoredList) -> list[CategoryProblem]:
    known = {category.id for category in stored.categories}
    seen: set[uuid.UUID] = set()
    found: list[CategoryProblem] = []
    for index, item in enumerate(items):
        if item.id is None:
            continue
        if item.id not in known:
            found.append(CategoryProblem(rule="id_unknown", field="id", index=index, position=None, other_index=None))
        elif item.id in seen:
            found.append(CategoryProblem(rule="id_duplicate", field="id", index=index, position=None, other_index=None))
        seen.add(item.id)
    return found


def build(
    items: list[CategoryInput], new_id: Callable[[], uuid.UUID]
) -> tuple[list[StoredCategory], frozenset[uuid.UUID]]:
    """Turn a valid list into the rows to store: canonical names, trimmed descriptions, senders in stored form.

    The senders of a category are in the order of their entry (the order a read gives them).
    The returned ids are those of the new categories.

    Args:
        items: The valid categories in order.
        new_id: Makes the id of a category that has none.

    Returns:
        The categories in order and the ids that did not exist before.
    """
    created: set[uuid.UUID] = set()
    rows: list[StoredCategory] = []
    for item in items:
        category_id = item.id
        if category_id is None:
            category_id = new_id()
            created.add(category_id)
        rows.append(
            StoredCategory(
                category_id,
                canonical_text(item.name),
                item.description.strip(),
                item.kind,
                notify=item.notify,
                senders=_stored_senders(item.senders),
            )
        )
    return rows, frozenset(created)


def _stored_senders(senders: list[SenderItem]) -> tuple[StoredSender, ...]:
    """Return the entries of a valid category in stored form, ordered by entry."""
    parsed = [parse_entry(sender.entry, sender.subdomains) for sender in senders]
    return tuple(
        sorted(
            (StoredSender(entry.value, entry.is_domain, entry.subdomains) for entry in parsed if entry is not None),
            key=lambda sender: sender.entry,
        )
    )


def canonical_instructions(raw: str) -> str:
    """Return the stored form of the general instructions: trimmed (the length the rules measure)."""
    return raw.strip()


def is_unchanged(rows: list[StoredCategory], instructions: str, archive_label: str, stored: StoredList) -> bool:
    """Tell whether the new list equals the stored one: categories (kind, tick, senders), order, instructions, archive.

    Args:
        rows: The rows built from the request.
        instructions: The general instructions in their stored form.
        archive_label: The archive label name.
        stored: The stored list.

    Returns:
        True when saving would add nothing.
    """
    return (
        tuple(rows) == stored.categories
        and instructions == stored.general_instructions
        and archive_label == stored.archive_label
    )
