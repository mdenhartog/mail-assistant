import type { ReactElement } from "react";

import { Field } from "@/components/Field";
import { ARCHIVE_HELP } from "@/features/categories/copy";

export interface ArchiveLabelFieldProps {
  value: string;
  error: string | undefined;
  readOnly: boolean;
  onChange: (value: string) => void;
}

/** The name of the archive label; it is saved with the list, and the api says why a name is refused. */
export function ArchiveLabelField({ value, error, readOnly, onChange }: ArchiveLabelFieldProps): ReactElement {
  return (
    <Field error={error} hint={ARCHIVE_HELP} label="Archive label">
      {(control) => (
        <input
          {...control}
          autoComplete="off"
          className="min-h-11 w-full min-w-0 rounded-control border border-border bg-surface-raised px-3 py-2 text-text aria-invalid:border-2 aria-invalid:border-danger read-only:opacity-80"
          data-field="archiveLabel"
          onChange={(event) => {
            onChange(event.target.value);
          }}
          readOnly={readOnly}
          spellCheck={false}
          type="text"
          value={value}
        />
      )}
    </Field>
  );
}
