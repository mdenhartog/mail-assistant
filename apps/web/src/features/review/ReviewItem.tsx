import { memo } from "react";
import type { ReactElement } from "react";

import type { PlanItem } from "@/api/plan/plan.types";
import { DECISION_TEXT, confidenceText, pairText } from "@/features/review/copy";
import { cleanText } from "@/features/review/text";

function cleanName(name: string | null): string | null {
  return name === null ? null : cleanText(name);
}

export interface ReviewItemProps {
  row: PlanItem;
  checked: boolean;
  onToggle: (id: number) => void;
}

/**
 * One mail: a tick box whose whole row is the target, the sender name with the real address beside it, the subject
 * in full, and the decision in words. Everything from outside is cleaned and rendered as text (AC-44, ADR-0044).
 * Memoised so ticking one box does not redraw the other rows, which also keeps focus where it is.
 */
export const ReviewItem = memo(function ReviewItem({ row, checked, onToggle }: ReviewItemProps): ReactElement {
  return (
    <li className="flex flex-col gap-1 border-t border-divider py-2 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
      <label className="flex min-h-11 min-w-0 flex-1 cursor-pointer items-start gap-3">
        <input
          checked={checked}
          className="size-11 flex-none accent-primary lg:size-6"
          onChange={() => {
            onToggle(row.id);
          }}
          type="checkbox"
        />
        <span className="min-w-0 py-2 wrap-anywhere">
          <span className="block font-semibold text-text">{cleanText(row.senderName)}</span>
          <span className="block text-sm text-text-muted">{cleanText(row.senderAddress)}</span>
          <span className="block text-text">{cleanText(row.subject)}</span>
          <span className="mt-1 block text-sm text-text-muted">{pairText("From", cleanName(row.oldTopic), cleanName(row.oldExtra))}</span>
          <span className="block text-sm text-text-muted">{pairText("To", cleanName(row.newTopic), cleanName(row.newExtra))}</span>
          {row.confidencePct === null ? null : <span className="block text-sm text-text-muted">{confidenceText(row.confidencePct)}</span>}
        </span>
      </label>
      <span className="ml-8 text-sm font-semibold text-text-muted sm:ml-0 sm:py-3">{DECISION_TEXT[row.decision]}</span>
    </li>
  );
});
