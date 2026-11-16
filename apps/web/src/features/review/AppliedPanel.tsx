import { useState } from "react";
import type { ReactElement } from "react";

import { classifyPlanError } from "@/api/plan/plan.api";
import { usePlanItems, useMoveBack } from "@/api/plan/plan.queries";
import type { PlanItem } from "@/api/plan/plan.types";
import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { FAILED_FALLBACK, SKIPPED_FALLBACK, clockText, dayText } from "@/features/review/copy";
import { cleanText } from "@/features/review/text";

function NotMoved({ rows }: { rows: PlanItem[] }): ReactElement | null {
  const skipped = rows.filter((row) => row.state === "skipped");
  const failed = rows.filter((row) => row.state === "failed");
  if (skipped.length + failed.length === 0) {
    return null;
  }
  return (
    <div className="mt-6">
      <h2 className="font-display text-xl text-text">Not moved</h2>
      <p className="mt-2 text-text">{`${String(skipped.length)} skipped, ${String(failed.length)} failed.`}</p>
      <p className="mt-1 text-text-muted">
        Mails you changed yourself stay as you left them. Mails Gmail did not accept stay where they were.
      </p>
      <ul className="mt-3 flex flex-col gap-3">
        {[...skipped, ...failed].map((row) => (
          <li key={row.id}>
            <Card>
              <p className="font-semibold text-text wrap-anywhere">{cleanText(row.senderName)}</p>
              <p className="text-sm text-text-muted wrap-anywhere">{cleanText(row.senderAddress)}</p>
              <p className="text-text wrap-anywhere">{cleanText(row.subject)}</p>
              <p className="mt-1 text-sm font-semibold text-text-muted">
                {row.state === "failed" ? "Failed: " : "Skipped: "}
                <span className="font-normal">{cleanText(row.reason ?? (row.state === "failed" ? FAILED_FALLBACK : SKIPPED_FALLBACK))}</span>
              </p>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}

function MovedBack({ processed, conflict }: { processed: boolean; conflict: boolean }): ReactElement {
  if (conflict) {
    return (
      <Banner kind="info" title="Moving back was already asked for.">
        The assistant restores the old labels. Nothing more to do.
      </Banner>
    );
  }
  return processed ? (
    <Banner kind="success" title="Your mails were moved back.">
      The old labels are restored.
    </Banner>
  ) : (
    <Banner kind="info" title="Your mails are being moved back.">
      The assistant restores the old labels. This takes a few minutes. Mails you changed yourself are left alone.
    </Banner>
  );
}

interface AskResult {
  requested: boolean;
  already: boolean;
  failed: boolean;
  processed: boolean;
}

function MoveBackResult({ result, onAsk }: { result: AskResult; onAsk: () => void }): ReactElement {
  if (result.requested) {
    return <MovedBack conflict={result.already} processed={result.processed} />;
  }
  return (
    <>
      <Button onClick={onAsk}>Move back</Button>
      {result.failed ? (
        <div className="mt-3">
          <Banner kind="danger" title="Could not move back.">
            Nothing was changed. Try again.
          </Banner>
        </div>
      ) : null}
    </>
  );
}

/** "Move back" with its red confirmation, and what the assistant says once it was asked. */
function MoveBackControl({ planId }: { planId: string }): ReactElement {
  const moveBack = useMoveBack();
  const [asking, setAsking] = useState(false);
  const already = moveBack.isError && classifyPlanError(moveBack.error).kind === "conflict";
  const result = {
    requested: moveBack.isSuccess || already,
    already,
    failed: moveBack.isError && !already,
    processed: moveBack.data?.processed ?? false,
  };
  return (
    <div className="mt-6">
      <MoveBackResult
        onAsk={() => {
          setAsking(true);
        }}
        result={result}
      />
      <ConfirmDialog
        cancelLabel="Keep as it is"
        confirmLabel="Move back"
        onCancel={() => {
          setAsking(false);
        }}
        onConfirm={() => {
          setAsking(false);
          moveBack.mutate(planId);
        }}
        open={asking}
        title="Move these mails back?"
        tone="danger"
      >
        <p>Every mail this review moved gets its old label again. Mails you changed yourself since then are left alone.</p>
      </ConfirmDialog>
    </div>
  );
}

function movedTitle(appliedAt: string | null): string {
  const day = dayText(appliedAt);
  const clock = clockText(appliedAt);
  return day === null || clock === null ? "Your mails were moved." : `Your mails were moved on ${day} at ${clock}.`;
}

export interface AppliedPanelProps {
  /** The plan Move back applies to. */
  planId: string;
  /** When the mails were moved (ISO time), shown as "15 Nov at 14:20", or null when unknown. */
  appliedAt: string | null;
}

/**
 * The result of an applied plan: what was moved, the mails that were skipped or failed with a plain reason, and
 * "Move back" behind a red confirmation (the label changes are undone, never mail deleted).
 */
export function AppliedPanel({ planId, appliedAt }: AppliedPanelProps): ReactElement {
  const items = usePlanItems(null, true);
  const rows = items.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section className="mt-6">
      <Banner kind="success" title={movedTitle(appliedAt)}>
        Only labels changed; nothing was deleted.
      </Banner>
      <NotMoved rows={rows} />
      <MoveBackControl planId={planId} />
    </section>
  );
}
