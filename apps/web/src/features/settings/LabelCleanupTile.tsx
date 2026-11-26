import { useId, useState } from "react";
import type { ReactElement } from "react";

import { Card } from "@/components/Card";
import { Field } from "@/components/Field";
import { FieldGroup } from "@/components/FieldGroup";
import { rangeText } from "@/features/settings/cleanupText";
import type { FieldErrors } from "@/features/settings/fieldErrors";
import type { FieldKey, NumberKey, Ranges, SettingsValues } from "@/features/settings/useSettings";

interface LabelCleanupTileProps {
  values: SettingsValues;
  ranges: Ranges;
  errors: FieldErrors;
  readOnly: boolean;
  setField: (field: FieldKey, value: number) => void;
}

interface Aria {
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
}

const CONTROL =
  "min-h-11 min-w-0 max-w-full w-full rounded-control border border-border bg-surface-raised px-3 py-2 text-text tabular-nums " +
  "aria-invalid:border-2 aria-invalid:border-danger read-only:opacity-80";

const MINUTES_PER_HOUR = 60;

/** A whole number from typed text; anything else (empty, a sign, a fraction) counts as 0, which no range accepts. */
function parseWhole(text: string): number {
  return /^\d+$/.test(text.trim()) ? Number(text) : 0;
}

interface WholeNumberProps extends Aria {
  id: string;
  value: number;
  readOnly: boolean;
  onChange: (value: number) => void;
}

/**
 * A whole-number input that keeps what is typed (an empty field stays empty) while the draft holds the number.
 * When the draft changes from outside (a reset, "Use mine"), the text follows.
 */
function WholeNumber({ value, readOnly, onChange, ...aria }: WholeNumberProps): ReactElement {
  const [text, setText] = useState(String(value));
  if (parseWhole(text) !== value) {
    setText(String(value));
  }
  return (
    <input
      {...aria}
      className={CONTROL}
      inputMode="numeric"
      min={0}
      onChange={(event) => {
        if (!readOnly) {
          setText(event.target.value);
          onChange(parseWhole(event.target.value));
        }
      }}
      readOnly={readOnly}
      step={1}
      type="number"
      value={text}
    />
  );
}

interface UnitInputProps {
  label: string;
  value: number;
  readOnly: boolean;
  control: Aria;
  onChange: (value: number) => void;
}

function UnitInput({ label, value, readOnly, control, onChange }: UnitInputProps): ReactElement {
  const id = useId();
  return (
    <div className="flex min-w-0 max-w-full flex-1 flex-col gap-1 sm:max-w-40">
      <label className="text-sm font-semibold text-text" htmlFor={id}>
        {label}
      </label>
      <WholeNumber {...control} id={id} onChange={onChange} readOnly={readOnly} value={value} />
    </div>
  );
}

/** The waiting time is stored in minutes and typed as hours and minutes; either box carries over into the other. */
function WaitingTime({ values, ranges, errors, readOnly, setField }: LabelCleanupTileProps): ReactElement {
  const total = values.waitingMinutes;
  return (
    <FieldGroup
      error={errors.waitingMinutes}
      hint={`How long a label stays empty before I delete it. ${rangeText("waitingMinutes", ranges)}.`}
      legend="Waiting time before a delete"
    >
      {(control) => (
        <div className="flex flex-wrap items-end gap-x-3 gap-y-3">
          <UnitInput
            control={control}
            label="Hours"
            onChange={(hours) => {
              setField("waitingMinutes", hours * MINUTES_PER_HOUR + (total % MINUTES_PER_HOUR));
            }}
            readOnly={readOnly}
            value={Math.floor(total / MINUTES_PER_HOUR)}
          />
          <UnitInput
            control={control}
            label="Minutes"
            onChange={(minutes) => {
              setField("waitingMinutes", Math.floor(total / MINUTES_PER_HOUR) * MINUTES_PER_HOUR + minutes);
            }}
            readOnly={readOnly}
            value={total % MINUTES_PER_HOUR}
          />
        </div>
      )}
    </FieldGroup>
  );
}

interface DaysProps extends LabelCleanupTileProps {
  field: Exclude<NumberKey, "waitingMinutes">;
  label: string;
  hint: string;
}

function Days({ field, label, hint, values, ranges, errors, readOnly, setField }: DaysProps): ReactElement {
  return (
    <Field error={errors[field]} hint={`${hint} ${rangeText(field, ranges)}.`} label={label}>
      {(control) => (
        <WholeNumber
          {...control}
          onChange={(days) => {
            setField(field, days);
          }}
          readOnly={readOnly}
          value={values[field]}
        />
      )}
    </Field>
  );
}

/**
 * The "Label cleanup" tile: when the agent deletes an empty label, how long a label that left the list
 * is kept, and how long the record of deleted labels lives. Ranges and defaults come from the api.
 * The numbers are saved with the rest of the form.
 */
export function LabelCleanupTile(props: LabelCleanupTileProps): ReactElement {
  const heading = useId();
  return (
    <Card>
      <section aria-labelledby={heading} className="flex flex-col gap-5">
        <h2 className="font-display text-xl text-text" id={heading}>
          Label cleanup
        </h2>
        <WaitingTime {...props} />
        <Days
          {...props}
          field="protectionDays"
          hint="How long a label that left your list is kept, even when it is empty."
          label="Protection period (days)"
        />
        <Days
          {...props}
          field="retentionDays"
          hint="How long the list of deleted labels and the rename backup are kept."
          label="Retention (days)"
        />
      </section>
    </Card>
  );
}
