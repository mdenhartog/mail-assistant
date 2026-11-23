import { useId, useRef, useState } from "react";
import type { ReactElement } from "react";

import type { Decision, PlanGroup } from "@/api/plan/plan.types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { countText } from "@/features/review/copy";
import { GroupPanel } from "@/features/review/GroupPanel";
import type { SelectionUpdate, TipTarget } from "@/features/review/GroupPanel";
import { cleanText, groupKey } from "@/features/review/text";

export interface ReviewGroupProps {
  group: PlanGroup;
  title: string;
  target: TipTarget;
  selected: ReadonlySet<number>;
  busy: boolean;
  onSelection: (key: string, update: SelectionUpdate) => void;
  onDecideGroup: (group: PlanGroup, decision: Decision) => void;
  onDecideSelected: (group: PlanGroup, decision: Decision, ids: number[]) => void;
}

/** What the user decided for the group, in words. The server counts approved and rejected mails, so it survives a reload. */
function statusText(group: PlanGroup): string {
  const { approved, rejected, count } = group;
  const stay = rejected >= count ? "Stays in place" : `${String(rejected)} of ${String(count)} stay in place`;
  if (approved >= count) {
    return `All ${String(count)} will move`;
  }
  if (approved === 0) {
    return rejected === 0 ? "Not decided yet" : stay;
  }
  const move = `${String(approved)} of ${String(count)} will move`;
  return rejected === 0 ? move : `${move}, ${String(rejected)} stay in place`;
}

/** The first mail of the group as one line of plain text (React escapes it); no address, it is long and not needed. */
function exampleText(group: PlanGroup): string {
  return `For example: ${cleanText(group.example.senderName)}, "${cleanText(group.example.subject)}"`;
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
        <p className="mt-1 text-sm text-text-muted wrap-anywhere">{exampleText(group)}</p>
        <p className="mt-1">
          <span className="inline-flex rounded-pill border border-border px-3 text-sm font-semibold text-text">
            {statusText(group)}
          </span>
        </p>
        <GroupActions
          busy={busy}
          onApprove={() => {
            onDecideGroup(group, "approved");
          }}
          onKeep={() => {
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
