import type { ReactElement } from "react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import type { Summary } from "@/features/categories/rows";

export interface SaveSummaryProps {
  open: boolean;
  summary: Summary;
  onConfirm: () => void;
  onCancel: () => void;
}

function partsOf({ renamed, described, added, removed }: Summary): string[] {
  const counts: [number, string][] = [
    [renamed, "renamed"],
    [described, "with a new description"],
    [added, "added"],
    [removed, "removed"],
  ];
  return counts.filter(([count]) => count > 0).map(([count, what]) => `${String(count)} ${what}`);
}

/**
 * What a save does, before it does it. In R1 no review exists, so every save is a plain change of the list
 * that applies to new mail; the "creates a review" and "replaces the review" texts arrive with R2.
 */
export function SaveSummary({ open, summary, onConfirm, onCancel }: SaveSummaryProps): ReactElement {
  return (
    <ConfirmDialog
      cancelLabel="Keep editing"
      confirmLabel="Save"
      onCancel={onCancel}
      onConfirm={onConfirm}
      open={open}
      title="Save these changes?"
      tone="safe"
    >
      <p>{partsOf(summary).join(", ")}.</p>
      <p className="mt-2">Renaming only changes the label name.</p>
      <p className="mt-2">Changes apply to new mail from now on. Old mail stays where it is for now.</p>
    </ConfirmDialog>
  );
}
