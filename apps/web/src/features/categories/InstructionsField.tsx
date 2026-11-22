import { useId } from "react";
import type { ReactElement } from "react";

import { Field } from "@/components/Field";
import { HELP } from "@/features/categories/copy";
import { MAX_INSTRUCTIONS } from "@/features/categories/policy";

export interface InstructionsFieldProps {
  value: string;
  error: string | undefined;
  readOnly: boolean;
  onChange: (value: string) => void;
}

/** The general instructions of the whole list, with a live count. */
export function InstructionsField({ value, error, readOnly, onChange }: InstructionsFieldProps): ReactElement {
  const countId = useId();
  return (
    <Field error={error} hint={HELP.instructions} label="General instructions">
      {(control) => (
        <div className="flex flex-col gap-1">
          <textarea
            {...control}
            aria-describedby={[control["aria-describedby"], countId].filter(Boolean).join(" ")}
            className="field-sizing-content min-h-24 w-full min-w-0 max-w-full rounded-control border border-border bg-surface-raised px-3 py-2 text-text aria-invalid:border-2 aria-invalid:border-danger read-only:opacity-80"
            data-field="instructions"
            onChange={(event) => {
              onChange(event.target.value);
            }}
            readOnly={readOnly}
            rows={4}
            value={value}
          />
          <p className="text-sm text-text-muted" id={countId}>
            {`${String(Array.from(value).length)} of ${String(MAX_INSTRUCTIONS)}`}
          </p>
        </div>
      )}
    </Field>
  );
}
