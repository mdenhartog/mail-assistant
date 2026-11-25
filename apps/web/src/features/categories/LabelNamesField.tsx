import type { ReactElement } from "react";

import { Field } from "@/components/Field";
import { ARCHIVE_HELP, OTHER_HELP } from "@/features/categories/copy";
import type { CategoriesFlow } from "@/features/categories/useCategoriesFlow";
import type { CategoriesSave } from "@/features/categories/useCategoriesSave";

interface NameFieldProps {
  label: string;
  hint: string;
  /** Marks the input for the page's own queries (focus on error). */
  dataField: string;
  value: string;
  error: string | undefined;
  readOnly: boolean;
  onChange: (value: string) => void;
}

/** One label name: a text field with its help text and, when the api refused the name, the reason tied to it. */
function NameField({ label, hint, dataField, value, error, readOnly, onChange }: NameFieldProps): ReactElement {
  return (
    <Field error={error} hint={hint} label={label}>
      {(control) => (
        <input
          {...control}
          autoComplete="off"
          className="min-h-11 w-full min-w-0 rounded-control border border-border bg-surface-raised px-3 py-2 text-text aria-invalid:border-2 aria-invalid:border-danger read-only:opacity-80"
          data-field={dataField}
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

export interface LabelNamesFieldProps {
  flow: Pick<CategoriesFlow, "settings" | "setOtherLabel" | "setArchiveLabel">;
  save: Pick<CategoriesSave, "saving" | "otherError" | "archiveError" | "clearOther" | "clearArchive">;
}

/** The names of the "Other" label and the archive label; they are saved with the list, and the api says why a name is refused. */
export function LabelNamesField({ flow, save }: LabelNamesFieldProps): ReactElement {
  return (
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
      <NameField
        dataField="otherLabel"
        error={save.otherError}
        hint={OTHER_HELP}
        label="Other label"
        onChange={(value) => {
          flow.setOtherLabel(value);
          save.clearOther();
        }}
        readOnly={save.saving}
        value={flow.settings.otherLabel}
      />
      <NameField
        dataField="archiveLabel"
        error={save.archiveError}
        hint={ARCHIVE_HELP}
        label="Archive label"
        onChange={(value) => {
          flow.setArchiveLabel(value);
          save.clearArchive();
        }}
        readOnly={save.saving}
        value={flow.settings.archiveLabel}
      />
    </div>
  );
}
