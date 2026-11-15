import type { ReactElement } from "react";

import type { CategoryItem } from "@/api/categories/categories.types";
import type { PlanView } from "@/api/plan/plan.types";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { countText, moveLabel } from "@/features/review/copy";
import { groupKey, groupTitle } from "@/features/review/text";

export interface ApproveDialogProps {
  open: boolean;
  plan: PlanView;
  categories: readonly CategoryItem[];
  tally: Readonly<Record<string, number>>;
  onConfirm: () => void;
  onCancel: () => void;
}

/** What the summary says per group, then the mails approved one by one, which the server counts only as a total. */
function lines(plan: PlanView, categories: readonly CategoryItem[], tally: Readonly<Record<string, number>>): string[] {
  const known = plan.groups.flatMap((group) => {
    const count = tally[groupKey(group)] ?? 0;
    return count > 0 ? [{ text: `${groupTitle(group, categories)}: ${countText(count)}`, count }] : [];
  });
  const rest = plan.counts.approved - known.reduce((sum, entry) => sum + entry.count, 0);
  const text = known.map((entry) => entry.text);
  return rest > 0 ? [...text, `Picked one by one: ${countText(rest)}`] : text;
}

/**
 * The summary before anything is approved (AC-55): the counts per group, that only labels change and that the user can
 * move back. A normal confirm button, because nothing is deleted or replaced; the safe button comes first.
 */
export function ApproveDialog({ open, plan, categories, tally, onConfirm, onCancel }: ApproveDialogProps): ReactElement {
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
        {lines(plan, categories, tally).map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <p className="mt-3">Only labels change. Nothing is deleted, and you can move back afterwards.</p>
      <p className="mt-3">Mails you did not approve stay where they are.</p>
      <p className="mt-3">
        When many mails move within a day, the move waits a while first. You can cancel it in Telegram until it starts.
      </p>
    </ConfirmDialog>
  );
}
