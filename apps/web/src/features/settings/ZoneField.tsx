import type { ReactElement } from "react";

import { Field } from "@/components/Field";
import { ZoneCombobox } from "@/features/settings/ZoneCombobox";

interface ZoneFieldProps {
  value: string;
  onChange: (value: string) => void;
  readOnly: boolean;
  error: string | undefined;
  /** The zone as stored; the second Escape puts it back. Defaults to the current value. */
  savedValue?: string | undefined;
  /** The clock for the live local time. Defaults to the system clock. */
  now?: (() => Date) | undefined;
}

function systemNow(): Date {
  return new Date();
}

/** The Time zone field: label, hint and the zone combobox. */
export function ZoneField({ value, onChange, readOnly, error, savedValue, now }: ZoneFieldProps): ReactElement {
  return (
    <Field error={error} hint="The times below are local times in this zone." label="Time zone">
      {(control) => (
        <ZoneCombobox
          control={control}
          now={now ?? systemNow}
          onChange={onChange}
          readOnly={readOnly}
          savedValue={savedValue ?? value}
          value={value}
        />
      )}
    </Field>
  );
}
