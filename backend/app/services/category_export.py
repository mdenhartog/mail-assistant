"""Export of the category list and the template files (U-label-structure-13, ADR-0058).

The export is written by ``category_policy`` from the stored list of one mailbox and carries only the fields of the
upload file: no id, no count, no version. The template and the example are the files of the shared package.
"""

import asyncio
from pathlib import Path
from typing import Final, Literal

from app.categories_repo import CategoriesRepository
from category_policy.senders import SenderEntry
from category_policy.yaml_file import FileCategory, ParsedList, dump_category_file

EXPORT_NAME: Final = "mail-categories.yaml"
TemplateKind = Literal["template", "example"]
_TEMPLATE_DIR: Final = Path(__file__).resolve().parents[3] / "packages" / "category-policy" / "template"
TEMPLATE_NAMES: Final[dict[TemplateKind, str]] = {
    "template": "mail-categories.template.yaml",
    "example": "mail-categories.example.yaml",
}


class NoList(Exception):  # noqa: N818  # a state of the mailbox, not a fault
    """There is no list to export yet (the agent has not written version 1)."""


async def export_list(repository: CategoriesRepository) -> bytes:
    """Write the stored list as a schema 1 file.

    Args:
        repository: The repository of the mailbox.

    Returns:
        The UTF-8 content of ``mail-categories.yaml``.

    Raises:
        NoList: There is no list yet.
    """
    stored = await repository.read()
    if stored.version == 0:
        raise NoList
    parsed = ParsedList(
        general_instructions=stored.general_instructions,
        archive_label=stored.archive_label,
        categories=tuple(
            FileCategory(
                name=category.name,
                description=category.description,
                kind=category.kind,
                senders=tuple(SenderEntry(text=s.entry, subdomains=s.subdomains) for s in category.senders),
                notify=category.notify,
            )
            for category in stored.categories
        ),
    )
    return dump_category_file(parsed)


async def template_file(kind: TemplateKind) -> bytes:
    """Read the template or the example file.

    Args:
        kind: Which file.

    Returns:
        The content of the file.
    """
    return await asyncio.to_thread((_TEMPLATE_DIR / TEMPLATE_NAMES[kind]).read_bytes)
