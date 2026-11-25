import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import { Link } from "react-router";

import { classifyRenameError } from "@/api/categories/rename.api";
import { useRestoreRename } from "@/api/categories/rename.queries";
import type { RenameFailure, RenameItem, RenamePreview } from "@/api/categories/rename.types";
import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { RESULT } from "@/features/categories/rename/copy";
import { paths } from "@/router/paths";

function describe(item: RenameItem): string {
  switch (item.itemState) {
    case "done":
      return item.action === "merge" ? RESULT.merged(item.oldName, item.newName) : RESULT.renamed(item.oldName, item.newName);
    case "skipped":
      return RESULT.skipped(item.oldName);
    default:
      // ASSUMPTION: "kept" is an entry the agent left alone because its name changed by hand after the preview (R5).
      return RESULT.kept(item.oldName);
  }
}

function count(items: readonly RenameItem[], state: RenameItem["itemState"]): number {
  return items.filter((item) => item.itemState === state).length;
}

type Outcome = { kind: "requested" } | { kind: "failed"; failure: RenameFailure };

function OutcomeBanner({ outcome }: { outcome: Outcome }): ReactElement {
  if (outcome.kind === "requested") {
    return (
      <Banner focusOnMount kind="success" title={RESULT.requested}>
        {RESULT.requestedBody}
      </Banner>
    );
  }
  switch (outcome.failure) {
    case "nothing-to-restore":
      return (
        <Banner focusOnMount kind="info" title={RESULT.nothing}>
          {RESULT.nothingBody}
        </Banner>
      );
    case "session":
      return (
        <Banner focusOnMount kind="danger" title="Your session ended.">
          Sign in again, then come back to this page.{" "}
          <Link className="inline-flex min-h-11 items-center underline" to={paths.loginExpired}>
            Sign in again
          </Link>
        </Banner>
      );
    default:
      return (
        <Banner focusOnMount kind="danger" title={RESULT.failed}>
          {RESULT.failedBody}
        </Banner>
      );
  }
}

interface Restore {
  asking: boolean;
  setAsking: (asking: boolean) => void;
  pending: boolean;
  outcome: Outcome | null;
  send: () => void;
}

/** Asks for the old names once; nothing goes while a request is pending or after one was accepted. */
function useRestore(): Restore {
  const [asking, setAsking] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const restore = useRestoreRename();
  const send = (): void => {
    setAsking(false);
    if (restore.isPending || outcome?.kind === "requested") {
      return;
    }
    setOutcome(null);
    restore.mutate(undefined, {
      onSuccess: () => {
        setOutcome({ kind: "requested" });
      },
      onError: (error) => {
        setOutcome({ kind: "failed", failure: classifyRenameError(error, "restore") });
      },
    });
  };
  return { asking, setAsking, pending: restore.isPending, outcome, send };
}

/** The finished rename: what happened to each label, the stale-name notice and Restore. */
export function RenameResult({ preview, focusOnMount }: { preview: RenamePreview; focusOnMount: boolean }): ReactElement {
  const section = useRef<HTMLElement>(null);
  const restore = useRestore();
  const { items } = preview;

  useEffect(() => {
    if (focusOnMount) {
      section.current?.focus();
    }
  }, [focusOnMount]);

  return (
    <section aria-labelledby="rename-result" className="flex flex-col gap-3" ref={section} tabIndex={-1}>
      <h3 className="font-display text-lg text-text" id="rename-result">
        {RESULT.title}
      </h3>
      <p className="font-semibold text-text">
        {RESULT.summary(count(items, "done"), items.length, count(items, "skipped"), count(items, "kept"))}
      </p>
      <p className="text-text">{RESULT.notice}</p>
      <ul className="flex flex-col gap-1 text-text">
        {items.map((item) => (
          <li className="wrap-anywhere" key={item.id}>
            {describe(item)}
          </li>
        ))}
      </ul>
      {restore.outcome === null ? null : <OutcomeBanner outcome={restore.outcome} />}
      <div className="flex flex-col items-start gap-2">
        <Button
          aria-describedby="rename-restore-help"
          disabled={restore.outcome?.kind === "requested"}
          loading={restore.pending}
          loadingLabel={RESULT.restoreSending}
          onClick={() => {
            restore.setAsking(true);
          }}
          variant="secondary"
        >
          {RESULT.restore}
        </Button>
        <p className="text-sm text-text-muted" id="rename-restore-help">
          {RESULT.restoreHelp}
        </p>
      </div>
      <ConfirmDialog
        cancelLabel={RESULT.dialogCancel}
        confirmLabel={RESULT.dialogConfirm}
        onCancel={() => {
          restore.setAsking(false);
        }}
        onConfirm={restore.send}
        open={restore.asking}
        title={RESULT.dialogTitle}
        tone="safe"
      >
        <p>{RESULT.dialogBody}</p>
      </ConfirmDialog>
    </section>
  );
}
