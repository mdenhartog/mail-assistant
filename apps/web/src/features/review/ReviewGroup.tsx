import { useId, useState } from "react";
import type { ReactElement } from "react";

import type { Decision, PlanGroup } from "@/api/plan/plan.types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { countText } from "@/features/review/copy";
import { GroupPanel } from "@/features/review/GroupPanel";
import type { SelectionUpdate } from "@/features/review/GroupPanel";
import { groupKey } from "@/features/review/text";

export interface ReviewGroupProps {
  group: PlanGroup;
  title: string;
  selected: ReadonlySet<number>;
  busy: boolean;
  onSelection: (key: string, update: SelectionUpdate) => void;
  onDecideGroup: (group: PlanGroup, decision: Decision) => void;
  onDecideSelected: (group: PlanGroup, decision: Decision, ids: number[]) => void;
}

/**
 * One group of mails that would move from one category to another. The header is a disclosure button (collapsed at
 * first) with the count; "Approve group" and "Keep all in place" sit beside it, on a row of their own on a narrow
 * screen. The panel stays mounted in the same place once opened, so the rows keep a stable DOM.
 */
export function ReviewGroup(props: ReviewGroupProps): ReactElement {
  const { group, title, busy, onDecideGroup } = props;
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <li data-group={groupKey(group)}>
      <Card>
        <h3 className="m-0 text-md">
          <button
            aria-controls={panelId}
            aria-expanded={open}
            className="flex min-h-11 w-full cursor-pointer flex-wrap items-center justify-between gap-2 rounded-control text-left font-display text-lg text-text"
            onClick={() => {
              setOpen((current) => !current);
            }}
            type="button"
          >
            <span className="min-w-0 wrap-anywhere">{title}</span>
            <span className="text-md font-semibold text-text-muted">{countText(group.count)}</span>
          </button>
        </h3>
        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <Button
            aria-label={`Approve group: ${title}`}
            disabled={busy}
            onClick={() => {
              onDecideGroup(group, "approved");
            }}
            variant="primary"
          >
            Approve group
          </Button>
          <Button
            aria-label={`Keep all in place: ${title}`}
            disabled={busy}
            onClick={() => {
              onDecideGroup(group, "rejected");
            }}
          >
            Keep all in place
          </Button>
        </div>
        <div hidden={!open} id={panelId}>
          {open ? <GroupPanel {...props} /> : null}
        </div>
      </Card>
    </li>
  );
}
