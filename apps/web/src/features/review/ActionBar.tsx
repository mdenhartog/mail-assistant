import type { ReactElement } from "react";

import { Button } from "@/components/Button";
import { moveLabel } from "@/features/review/copy";

export interface ActionBarProps {
  approved: number;
  undecided: number;
  onMove: () => void;
}

/**
 * The bar at the bottom of the review: the one button says what it does ("Move 80 mails, labels only"). With nothing
 * approved it stays in place but does nothing, and the text next to it says why. The page keeps scroll padding for it
 * (see `index.css`), so it never covers the box that has focus.
 */
export function ActionBar({ approved, undecided, onMove }: ActionBarProps): ReactElement {
  return (
    <div
      className="sticky bottom-0 z-10 -mx-6 mt-6 flex flex-col gap-3 border-t border-divider bg-surface-raised px-6 py-3 sm:flex-row sm:items-center sm:justify-between"
      data-action-bar=""
    >
      <p className="min-w-0 text-text wrap-anywhere">
        {approved === 0
          ? "Approve a group or tick mails first. Nothing moves until you confirm."
          : `${String(undecided)} not decided yet stay where they are.`}
      </p>
      <Button disabled={approved === 0} onClick={onMove} variant="primary">
        {moveLabel(approved)}
      </Button>
    </div>
  );
}
