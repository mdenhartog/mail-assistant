import type { ReactElement } from "react";

import type { CategoryItem } from "@/api/categories/categories.types";
import type { PlanView } from "@/api/plan/plan.types";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { countText, moveLabel } from "@/features/review/copy";
import { groupTitle } from "@/features/review/text";

export interface ApproveDialogProps {
  open: boolean;
  plan: PlanView;
  categories: readonly CategoryItem[];
  onConfirm: () => void;
  onCancel: () => void;
}

/** What the summary says per group: the approved count the server holds, so it is exact after a reload (AC-13). */
function lines(plan: PlanView, categories: readonly CategoryItem[]): string[] {
  return plan.groups
    .filter((group) => group.approved > 0)
    .map((group) => `${groupTitle(group, categories)}: ${countText(group.approved)}`);
}

/** The wait rule in words: the real numbers when the server sends them, else a neutral sentence. */
function waitText(plan: PlanView): string {
  const { applyThreshold, applyDelayMinutes } = plan;
  if (applyThreshold === null || applyDelayMinutes === null) {
    return "When many mails move within a day, the move waits a while first. You can cancel it in Telegram until it starts.";
  }
  return `More than ${String(applyThreshold)} mails in 24 hours: the move starts after ${String(applyDelayMinutes)} minutes so you can still cancel in Telegram.`;
}

/**
 * The summary before anything is approved (AC-55): the counts per group, that only labels change and that the user can
 * move back. A normal confirm button, because nothing is deleted or replaced; the safe button comes first.
 */
export function ApproveDialog({ open, plan, categories, onConfirm, onCancel }: ApproveDialogProps): ReactElement {
  const approved = plan.counts.approved;
  return (
    <ConfirmDialog
      cancelLabel="Not yet"
      confirmLabel={moveLabel(approved)}
      onCancel={onCancel}
      onConfirm={onConfirm}
      open={open}
      title={`Move ${countText(approved)}?`}
      tone="safe"
    >
      <ul className="list-disc pl-5">
        {lines(plan, categories).map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <p className="mt-3">Each mail gets its new category label in Gmail. Nothing is deleted and nothing is sent. You can move them back afterwards.</p>
      <p className="mt-3">Mails you did not approve stay where they are.</p>
      <p className="mt-3">{waitText(plan)}</p>
    </ConfirmDialog>
  );
}
