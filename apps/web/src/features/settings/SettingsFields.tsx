import { useId } from "react";
import type { ReactElement, ReactNode } from "react";

import { Field } from "@/components/Field";
import { FieldGroup } from "@/components/FieldGroup";
import { TimeField } from "@/components/TimeField";
import type { FieldErrors } from "@/features/settings/fieldErrors";
import { ZoneField } from "@/features/settings/ZoneField";
import type { FieldKey, SettingsValues } from "@/features/settings/useSettings";

interface SettingsFieldsProps {
  values: SettingsValues;
  errors: FieldErrors;
  readOnly: boolean;
  /** The zone as stored; Escape in the zone field puts it back. */
  savedZone: string;
  setField: (field: FieldKey, value: string) => void;
}

interface GroupControl {
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
}

function Card({ children }: { children: ReactNode }): ReactElement {
  return <div className="rounded-card bg-surface-raised p-5 shadow-soft">{children}</div>;
}

interface SingleTimeProps extends SettingsFieldsProps {
  label: string;
  hint: string;
  field: "overviewAt" | "remindAt";
}

function SingleTime({ label, hint, field, values, errors, readOnly, setField }: SingleTimeProps): ReactElement {
  return (
    <Card>
      <Field error={errors[field]} hint={hint} label={label}>
        {(control) => (
          <TimeField
            {...control}
            onChange={(value) => {
              setField(field, value);
            }}
            readOnly={readOnly}
            value={values[field]}
          />
        )}
      </Field>
    </Card>
  );
}

interface LabelledTimeProps {
  label: string;
  value: string;
  readOnly: boolean;
  control: GroupControl;
  onChange: (value: string) => void;
}

function LabelledTime({ label, value, readOnly, control, onChange }: LabelledTimeProps): ReactElement {
  const id = useId();
  return (
    <div className="flex min-w-0 max-w-full flex-col gap-1">
      <label className="text-sm font-semibold text-text" htmlFor={id}>
        {label}
      </label>
      <TimeField {...control} id={id} onChange={onChange} readOnly={readOnly} value={value} />
    </div>
  );
}

function QuietHours({ values, errors, readOnly, setField }: SettingsFieldsProps): ReactElement {
  return (
    <Card>
      <FieldGroup
        error={errors.quietStart ?? errors.quietEnd}
        hint="Alerts that arrive in this window wait until it ends."
        legend="Quiet hours"
      >
        {(control) => (
          <div className="flex flex-wrap items-end gap-x-3 gap-y-3">
            <LabelledTime
              control={control}
              label="From"
              onChange={(value) => {
                setField("quietStart", value);
              }}
              readOnly={readOnly}
              value={values.quietStart}
            />
            <span aria-hidden="true" className="pb-2 text-text-muted">
              until
            </span>
            <LabelledTime
              control={control}
              label="Until"
              onChange={(value) => {
                setField("quietEnd", value);
              }}
              readOnly={readOnly}
              value={values.quietEnd}
            />
          </div>
        )}
      </FieldGroup>
    </Card>
  );
}

/** The four settings in the order of the screens document: Time zone first, then the three times. */
export function SettingsFields(props: SettingsFieldsProps): ReactElement {
  const { values, errors, readOnly, savedZone, setField } = props;
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <Card>
        <ZoneField
          error={errors.timeZone}
          onChange={(value) => {
            setField("timeZone", value);
          }}
          readOnly={readOnly}
          savedValue={savedZone}
          value={values.timeZone}
        />
      </Card>
      <QuietHours {...props} />
      <SingleTime {...props} field="overviewAt" hint="When I send you the summary of your mail." label="Daily overview" />
      <SingleTime
        {...props}
        field="remindAt"
        hint="When a snoozed alert comes back if you do not name a time."
        label="Remind-me-later default"
      />
    </div>
  );
}
