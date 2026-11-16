import { useId, useRef, useState } from "react";
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

/** What the user decided for the group, in words. The server counts the approved mails; "kept" is this visit only. */
function statusText(group: PlanGroup, kept: boolean): string {
  if (group.approved >= group.count) {
    return `All ${String(group.count)} will move`;
  }
  if (group.approved > 0) {
    return `${String(group.approved)} of ${String(group.count)} will move`;
  }
  return kept ? "Stays in place" : "Not decided yet";
}

interface GroupActionsProps {
  title: string;
  busy: boolean;
  open: boolean;
  onApprove: () => void;
  onKeep: () => void;
  onLook: () => void;
}

/** The decisions of a group; "Look at these mails first" shows only while the group is closed. */
function GroupActions({ title, busy, open, onApprove, onKeep, onLook }: GroupActionsProps): ReactElement {
  return (
    <div className="mt-2 flex flex-col gap-2 sm:flex-row">
      <Button aria-label={`Approve group: ${title}`} disabled={busy} onClick={onApprove} variant="secondary">
        Approve group
      </Button>
      <Button aria-label={`Keep all in place: ${title}`} disabled={busy} onClick={onKeep}>
        Keep all in place
      </Button>
      {open ? null : (
        <Button aria-label={`Look at these mails first: ${title}`} onClick={onLook} variant="ghost">
          Look at these mails first
        </Button>
      )}
    </div>
  );
}

/**
 * One group of mails that would move from one category to another. The header is a disclosure button (collapsed at
 * first) with the count; "Approve group" and "Keep all in place" sit beside it, on a row of their own on a narrow
 * screen. The panel stays mounted in the same place once opened, so the rows keep a stable DOM.
 */
export function ReviewGroup(props: ReviewGroupProps): ReactElement {
  const { group, title, busy, onDecideGroup } = props;
  const [open, setOpen] = useState(false);
  const [kept, setKept] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  return (
    <li data-group={groupKey(group)}>
      <Card>
        <h3 className="m-0 text-md">
          <button
            ref={toggle}
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
        <p className="mt-1">
          <span className="inline-flex rounded-pill border border-border px-3 text-sm font-semibold text-text">
            {statusText(group, kept)}
          </span>
        </p>
        <GroupActions
          busy={busy}
          onApprove={() => {
            setKept(false);
            onDecideGroup(group, "approved");
          }}
          onKeep={() => {
            setKept(true);
            onDecideGroup(group, "rejected");
          }}
          onLook={() => {
            setOpen(true);
            toggle.current?.focus();
          }}
          open={open}
          title={title}
        />
        <div hidden={!open} id={panelId}>
          {open ? <GroupPanel {...props} /> : null}
        </div>
      </Card>
    </li>
  );
}
