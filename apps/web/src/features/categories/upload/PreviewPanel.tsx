import { useEffect, useId, useRef } from "react";
import type { ReactElement } from "react";

import type { UploadPreview } from "@/api/categories/upload.types";
import { Button } from "@/components/Button";
import { ChangeIcon } from "@/features/categories/upload/icons";
import type { ChangeKind } from "@/features/categories/upload/icons";

const REMOVED_SENTENCE = "Removed categories disappear from the app. Their Gmail labels and mail stay as they are.";

function Count({ kind, count }: { kind: ChangeKind; count: number }): ReactElement {
  return (
    <span className="inline-flex items-center gap-1 align-middle">
      <ChangeIcon kind={kind} />
      <strong className="font-bold">{`${String(count)} ${kind}`}</strong>
    </span>
  );
}

function RemovedBlock({ names }: { names: readonly string[] }): ReactElement {
  const id = useId();
  return (
    <section aria-labelledby={id} className="flex flex-col gap-2 rounded-control border border-border p-4">
      <h4 className="flex items-center gap-2 font-semibold text-text" id={id}>
        <ChangeIcon kind="removed" />
        <span className="min-w-0 wrap-anywhere">Removed categories</span>
      </h4>
      <p className="text-text">{REMOVED_SENTENCE}</p>
      <ul className="flex list-disc flex-col gap-1 pl-6 text-text">
        {names.map((name) => (
          <li className="wrap-anywhere" key={name}>
            {name}
          </li>
        ))}
      </ul>
    </section>
  );
}

export interface PreviewPanelProps {
  preview: UploadPreview;
  busy: boolean;
  onReplace: () => void;
  onCancel: () => void;
}

/**
 * What a confirm would change: the counts first, the removed categories in their own block, then Cancel and
 * the confirm button. Focus goes to the heading, so the confirm button is never the default focus.
 */
export function PreviewPanel({ preview, busy, onReplace, onCancel }: PreviewPanelProps): ReactElement {
  const id = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  const label = preview.removed > 0 ? `Replace my whole list (${String(preview.removed)} removed)` : "Replace my whole list";
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4 rounded-card bg-surface-raised p-5 shadow-soft">
      <h3 className="font-display text-xl text-text wrap-anywhere" id={id} ref={heading} tabIndex={-1}>
        Preview of your file
      </h3>
      <p className="text-text leading-8">
        <Count count={preview.added} kind="added" />
        {", "}
        <Count count={preview.changed} kind="changed" />
        {", "}
        <Count count={preview.removed} kind="removed" />
      </p>
      {preview.instructionsChanged ? <p className="text-text">The general instructions change too.</p> : null}
      {preview.archiveLabelChanged ? <p className="text-text">The archive label changes too.</p> : null}
      {preview.removed > 0 ? <RemovedBlock names={preview.removedCategories} /> : null}
      <p className="text-text-muted">Nothing is stored until you replace your list.</p>
      <div className="flex flex-wrap gap-3">
        <Button disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
        <Button loading={busy} loadingLabel="Replacing..." onClick={onReplace} variant="primary">
          {label}
        </Button>
      </div>
    </section>
  );
}
