import type { ReactElement } from "react";

import { Field } from "@/components/Field";
import { HELP } from "@/features/categories/copy";
import { KindField } from "@/features/categories/KindField";
import { NotifyField } from "@/features/categories/NotifyField";
import type { Row, RowPatch } from "@/features/categories/rows";
import type { RowErrors } from "@/features/categories/saveErrors";
import { SendersField } from "@/features/categories/SendersField";
import { senderErrors } from "@/features/categories/senders";
import type { SenderError } from "@/features/categories/senders";

export interface CategoryFieldsProps {
  row: Row;
  /** Every category of the draft, to see which entries another category already lists. */
  rows: readonly Row[];
  /** What the api or the last Save refused; typing in the category clears it. */
  errors: RowErrors;
  onChange: (patch: RowPatch) => void;
}

const TEXT_CONTROL =
  "w-full min-w-0 max-w-full rounded-control border border-border bg-surface-raised px-3 py-2 text-text " +
  "aria-invalid:border-2 aria-invalid:border-danger";

/** The senders of the row as errors: what can be seen now, and what a save or the api refused, without repeats. */
function sendersOf(row: Row, rows: readonly Row[], refused: RowErrors): SenderError[] {
  const seen = new Set<string>();
  return [...senderErrors(rows, row), ...(refused.senders ?? [])].filter((error) => {
    const key = `${String(error.line)}:${error.text}`;
    const fresh = !seen.has(key);
    seen.add(key);
    return fresh;
  });
}

/** The fields of the edit view: name, kind, description, the senders and the tick. */
export function CategoryFields({ row, rows, errors, onChange }: CategoryFieldsProps): ReactElement {
  return (
    <>
      <Field error={errors.name} hint={HELP.name} label="Name">
        {(control) => (
          <input
            {...control}
            className={`min-h-11 ${TEXT_CONTROL}`}
            data-field="name"
            onChange={(event) => {
              onChange({ name: event.target.value });
            }}
            type="text"
            value={row.name}
          />
        )}
      </Field>
      <KindField
        onChange={(kind) => {
          onChange({ kind });
        }}
        value={row.kind}
      />
      <Field error={errors.description} hint={HELP.description} label="Description">
        {(control) => (
          <textarea
            {...control}
            className={`field-sizing-content min-h-24 ${TEXT_CONTROL}`}
            data-field="description"
            onChange={(event) => {
              onChange({ description: event.target.value });
            }}
            rows={3}
            value={row.description}
          />
        )}
      </Field>
      <SendersField
        errors={sendersOf(row, rows, errors)}
        onChange={(sendersText) => {
          onChange({ sendersText });
        }}
        skipped={row.skipped}
        value={row.sendersText}
      />
      <NotifyField
        checked={row.notify}
        onChange={(notify) => {
          onChange({ notify });
        }}
      />
    </>
  );
}
