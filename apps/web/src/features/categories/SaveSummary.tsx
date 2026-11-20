import type { ReactElement } from "react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import type { Change } from "@/features/categories/rows";

export interface SaveSummaryProps {
  open: boolean;
  changes: readonly Change[];
  onConfirm: () => void;
  onCancel: () => void;
}

/** "1 change", "3 changes". */
export function changesText(count: number): string {
  return `${String(count)} ${count === 1 ? "change" : "changes"}`;
}

function lineOf(change: Change): string {
  switch (change.kind) {
    case "rename":
      return `Rename "${change.from}" to "${change.to}"`;
    case "describe":
      return `Change the description of "${change.name}"`;
    case "remove":
      return `Remove "${change.name}"`;
    case "add":
      return `Add "${change.name}"`;
  }
}

/**
 * What a save does, before it does it: each change by name. The page already says that new mail is filed
 * using the list, so this only adds the renaming note when a rename is among the changes.
 */
export function SaveSummary({ open, changes, onConfirm, onCancel }: SaveSummaryProps): ReactElement {
  return (
    <ConfirmDialog
      cancelLabel="Keep editing"
      confirmLabel="Save changes"
      onCancel={onCancel}
      onConfirm={onConfirm}
      open={open}
      title={`Save ${changesText(changes.length)}?`}
      tone="safe"
    >
      <ul className="list-disc pl-5">
        {changes.map((change) => (
          <li className="wrap-anywhere" key={lineOf(change)}>
            {lineOf(change)}
          </li>
        ))}
      </ul>
      {changes.some((change) => change.kind === "rename") ? <p className="mt-2">Renaming only changes the label name.</p> : null}
    </ConfirmDialog>
  );
}
