import { useId, useState } from "react";
import type { ReactElement } from "react";
import { Link } from "react-router";

import { classifyRenameError } from "@/api/categories/rename.api";
import { useConfirmRename } from "@/api/categories/rename.queries";
import type { RenameFailure, RenameItem, RenamePreview as Preview } from "@/api/categories/rename.types";
import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Field } from "@/components/Field";
import { labels, mails, RENAME } from "@/features/categories/rename/copy";
import { paths } from "@/router/paths";

type Order = "most" | "fewest";

function sorted(items: readonly RenameItem[], order: Order): RenameItem[] {
  const direction = order === "most" ? -1 : 1;
  return [...items].sort((a, b) => direction * (a.mailCount - b.mailCount) || a.oldName.localeCompare(b.oldName));
}

function Card({ item, skipped, onToggle }: { item: RenameItem; skipped: boolean; onToggle: () => void }): ReactElement {
  return (
    <li>
      <div
        aria-label={item.oldName}
        className={`flex flex-col gap-2 rounded-card bg-surface-raised p-5 shadow-soft ${skipped ? "border border-border" : ""}`}
        role="group"
      >
        <div>
          <p className="text-sm text-text-muted">{RENAME.now}</p>
          <p className="font-semibold text-text wrap-anywhere">{item.oldName}</p>
        </div>
        <div>
          <p className="text-sm text-text-muted">{RENAME.becomes}</p>
          <p className="font-semibold text-text wrap-anywhere">{item.newName}</p>
        </div>
        <p className="text-text">{mails(item.mailCount)}</p>
        {item.action === "merge" ? <p className="text-text">{RENAME.merge(item.mailCount)}</p> : null}
        {skipped ? <p className="text-sm text-text-muted">{RENAME.skipped}</p> : null}
        <label className="flex min-h-11 cursor-pointer items-center gap-1 text-text">
          <input
            aria-label={`${RENAME.skip} ${item.oldName}`}
            checked={skipped}
            className="size-11 flex-none cursor-pointer accent-primary"
            onChange={onToggle}
            type="checkbox"
          />
          <span aria-hidden="true">{RENAME.skip}</span>
        </label>
      </div>
    </li>
  );
}

function SortSelect({ order, onChange }: { order: Order; onChange: (next: Order) => void }): ReactElement {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label className="font-semibold text-text" htmlFor={id}>
        {RENAME.sort}
      </label>
      <select
        className="min-h-11 w-full rounded-control border border-border bg-surface-raised px-3 py-2 text-text sm:w-64"
        id={id}
        onChange={(event) => {
          onChange(event.target.value === "fewest" ? "fewest" : "most");
        }}
        value={order}
      >
        <option value="most">{RENAME.mostFirst}</option>
        <option value="fewest">{RENAME.fewestFirst}</option>
      </select>
    </div>
  );
}

function FailureBanner({ failure }: { failure: RenameFailure }): ReactElement {
  switch (failure) {
    case "changed":
      return (
        <Banner kind="conflict" title={RENAME.changed}>
          {RENAME.changedBody}
        </Banner>
      );
    case "unknown-skip":
      return (
        <Banner kind="conflict" title={RENAME.unknownSkip}>
          {RENAME.unknownSkipBody}
        </Banner>
      );
    case "session":
      return (
        <Banner kind="danger" title={RENAME.sessionEnded}>
          {RENAME.sessionEndedBody}{" "}
          <Link className="inline-flex min-h-11 items-center underline" to={paths.loginExpired}>
            {RENAME.signIn}
          </Link>
        </Banner>
      );
    default:
      return (
        <Banner kind="danger" title={RENAME.startFailed}>
          {RENAME.startFailedBody}
        </Banner>
      );
  }
}

interface TypedConfirmationProps {
  count: number;
  skippedCount: number;
  onConfirm: () => void;
  onCancel: () => void;
}

/** The dialog that asks the user to type the number of labels or RENAME before anything is sent. */
function TypedConfirmation({ count, skippedCount, onConfirm, onCancel }: TypedConfirmationProps): ReactElement {
  const [text, setText] = useState("");
  const [mismatch, setMismatch] = useState(false);
  const submit = (): void => {
    const typed = text.trim();
    if (typed === "RENAME" || typed === String(count)) {
      onConfirm();
    } else {
      setMismatch(true);
    }
  };
  return (
    <ConfirmDialog
      cancelLabel={RENAME.cancel}
      confirmLabel={RENAME.confirm}
      onCancel={onCancel}
      onConfirm={submit}
      open
      title={RENAME.dialogTitle(count)}
      tone="safe"
    >
      <p>{RENAME.dialogBody(count, skippedCount)}</p>
      <div className="mt-4">
        <Field error={mismatch ? RENAME.dialogMismatch(count) : undefined} hint={RENAME.dialogHint} label={RENAME.dialogField(count)}>
          {(control) => (
            <input
              {...control}
              autoComplete="off"
              className="min-h-11 w-full min-w-0 rounded-control border border-border bg-surface-raised px-3 py-2 text-text aria-invalid:border-2 aria-invalid:border-danger"
              onChange={(event) => {
                setText(event.target.value);
                setMismatch(false);
              }}
              spellCheck={false}
              type="text"
              value={text}
            />
          )}
        </Field>
      </div>
    </ConfirmDialog>
  );
}

interface PlanProps {
  preview: Preview;
  /** What the last confirmation said, kept by the section so it survives the reload of a changed plan. */
  failure: RenameFailure | null;
  onFailure: (failure: RenameFailure | null) => void;
}

function skippedAtStart(items: readonly RenameItem[]): Set<string> {
  return new Set(items.filter((item) => item.itemState === "skipped").map((item) => item.id));
}

interface Confirmation {
  pending: boolean;
  sent: boolean;
  send: () => void;
}

/** Sends the confirmation once: nothing goes while one is pending or after one was accepted. */
function useConfirmation(preview: Preview, skipped: ReadonlySet<string>, onFailure: (failure: RenameFailure | null) => void): Confirmation {
  const [sent, setSent] = useState(false);
  const confirm = useConfirmRename();
  const planHash = preview.planHash;
  const send = (): void => {
    if (planHash === null || confirm.isPending || sent) {
      return;
    }
    onFailure(null);
    confirm.mutate(
      { planHash, skippedIds: [...skipped] },
      {
        onSuccess: () => {
          setSent(true);
        },
        onError: (error) => {
          onFailure(classifyRenameError(error, "confirm"));
        },
      },
    );
  };
  return { pending: confirm.isPending, sent, send };
}

function useSkipped(items: readonly RenameItem[]): [Set<string>, (id: string) => void] {
  const [skipped, setSkipped] = useState<Set<string>>(() => skippedAtStart(items));
  const toggle = (id: string): void => {
    setSkipped((previous) => {
      const next = new Set(previous);
      if (!next.delete(id)) {
        next.add(id);
      }
      return next;
    });
  };
  return [skipped, toggle];
}

/** The pending plan as cards, a skip per label, and the typed confirmation. Keyed by the plan hash, so a changed plan starts afresh. */
export function RenamePreview({ preview, failure, onFailure }: PlanProps): ReactElement {
  const [order, setOrder] = useState<Order>("most");
  const [asking, setAsking] = useState(false);
  const [skipped, toggle] = useSkipped(preview.items);
  const confirmation = useConfirmation(preview, skipped, onFailure);
  const noteId = useId();
  const count = preview.items.length - skipped.size;

  return (
    <>
      <p className="text-text">{RENAME.intro}</p>
      <p className="font-semibold text-text">{RENAME.summary(preview.summary.labels, preview.summary.mails)}</p>
      <SortSelect onChange={setOrder} order={order} />
      <ul className="grid gap-4 sm:grid-cols-2">
        {sorted(preview.items, order).map((item) => (
          <Card
            item={item}
            key={item.id}
            onToggle={() => {
              toggle(item.id);
            }}
            skipped={skipped.has(item.id)}
          />
        ))}
      </ul>
      {failure === null ? null : <FailureBanner failure={failure} />}
      <div className="flex flex-col items-start gap-2">
        <Button
          aria-describedby={noteId}
          disabled={count === 0 || confirmation.sent || preview.planHash === null}
          loading={confirmation.pending}
          loadingLabel={RENAME.starting}
          onClick={() => {
            setAsking(true);
          }}
          variant="primary"
        >
          {RENAME.start}
        </Button>
        <p className="text-sm text-text-muted" id={noteId}>
          {count === 0 ? RENAME.allSkipped : `${RENAME.startHelp} ${labels(count)} will be renamed.`}
        </p>
      </div>
      {asking ? (
        <TypedConfirmation
          count={count}
          onCancel={() => {
            setAsking(false);
          }}
          onConfirm={() => {
            setAsking(false);
            confirmation.send();
          }}
          skippedCount={skipped.size}
        />
      ) : null}
    </>
  );
}
