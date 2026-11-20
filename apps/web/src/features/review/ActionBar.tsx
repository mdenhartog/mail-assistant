import { useId } from "react";
import type { ReactElement } from "react";

import { Button } from "@/components/Button";
import { StickyBar } from "@/components/StickyBar";
import { LABELS_ONLY_HELPER, moveLabel } from "@/features/review/copy";

export interface ActionBarProps {
  approved: number;
  undecided: number;
  onMove: () => void;
}

/**
 * The bar at the bottom of the review: the one button says what it does ("Move 80 mails to their new categories", with the helper line "Only labels change"). With nothing
 * approved it stays in place but does nothing, and the text next to it says why. The page keeps scroll padding for it
 * (`StickyBar`), so it never covers the box that has focus.
 */
export function ActionBar({ approved, undecided, onMove }: ActionBarProps): ReactElement {
  const helperId = useId();
  return (
    <StickyBar className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <p className="min-w-0 text-text wrap-anywhere">
        {approved === 0
          ? "Approve a group or tick mails first. Nothing moves until you confirm."
          : `${String(undecided)} not decided yet stay where they are.`}
      </p>
      <div className="flex flex-col items-start gap-1 sm:items-end">
        <Button aria-describedby={helperId} disabled={approved === 0} onClick={onMove} variant="primary">
          {moveLabel(approved)}
        </Button>
        <p className="text-sm text-text-muted" id={helperId}>
          {LABELS_ONLY_HELPER}
        </p>
      </div>
    </StickyBar>
  );
}
