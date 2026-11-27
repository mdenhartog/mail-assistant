"""The use cases of the label rename routes for one mailbox (U-label-prefix-removal-11, ADR-0061)."""

import uuid
from typing import TYPE_CHECKING

from app.schemas.label_rename import DeletedLabel, DeletedLabels, RenameItem, RenamePreview, RenameSummary

if TYPE_CHECKING:
    from app.clock import Clock
    from app.label_rename_repo import LabelRenameRepository


class LabelRename:
    """Shows the plan, confirms it, asks for the restore and lists the deleted labels."""

    def __init__(self, repository: "LabelRenameRepository", clock: "Clock") -> None:
        """Keep the repository and the clock."""
        self._repository = repository
        self._clock = clock

    async def preview(self) -> RenamePreview:
        """Return the plan with its state, hash and a summary (changes nothing)."""
        plan = await self._repository.plan()
        items = [
            RenameItem.model_validate(
                {
                    "id": i.label_id,
                    "oldName": i.old_name,
                    "newName": i.new_name,
                    "mailCount": i.mail_count,
                    "action": i.action,
                    "itemState": i.state,
                }
            )
            for i in plan.items
        ]
        summary = RenameSummary(labels=len(items), mails=sum(i.mail_count for i in items))
        return RenamePreview.model_validate(
            {"state": plan.state, "planHash": plan.plan_hash, "items": items, "summary": summary}
        )

    async def confirm(self, plan_hash: str, skipped_ids: list[str]) -> uuid.UUID:
        """Confirm the plan; see ``LabelRenameRepository.confirm`` for the refusals it raises."""
        return await self._repository.confirm(plan_hash, skipped_ids)

    async def restore(self) -> uuid.UUID:
        """Ask for the restore; see ``LabelRenameRepository.restore`` for the refusal it raises."""
        return await self._repository.restore()

    async def deleted(self) -> DeletedLabels:
        """Return the recently deleted labels within the retention period."""
        days, rows = await self._repository.deleted(self._clock.now())
        return DeletedLabels(
            retention_days=days, items=[DeletedLabel(name=r.name, deleted_at=r.deleted_at) for r in rows]
        )
