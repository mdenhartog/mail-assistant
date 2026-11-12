import type { ReactElement } from "react";

import { Field } from "@/components/Field";

interface ZoneFieldProps {
  value: string;
  onChange: (value: string) => void;
  readOnly: boolean;
  error: string | undefined;
}

const CONTROL =
  "min-h-11 w-full min-w-0 rounded-control border border-border bg-surface-raised px-3 text-text " +
  "aria-invalid:border-2 aria-invalid:border-danger read-only:opacity-80";

/**
 * Slot of U-web-settings-33, which rebuilds this file as a combobox with the same props. Here: a
 * plain text input for the zone name. The label "Time zone" and the hint stay.
 */
export function ZoneField({ value, onChange, readOnly, error }: ZoneFieldProps): ReactElement {
  return (
    <Field error={error} hint="The times below are local times in this zone." label="Time zone">
      {(control) => (
        <input
          {...control}
          autoCapitalize="none"
          autoComplete="off"
          className={CONTROL}
          maxLength={64}
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
