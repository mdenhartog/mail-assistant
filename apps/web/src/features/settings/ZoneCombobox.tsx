import type { ReactElement } from "react";

export interface ZoneControlProps {
  id: string;
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
}

export interface ZoneComboboxProps {
  control: ZoneControlProps;
  value: string;
  onChange: (value: string) => void;
  readOnly: boolean;
  savedValue: string;
  now: () => Date;
}

/** Skeleton of U-web-settings-33: a plain input until the combobox is built. */
export function ZoneCombobox({ control, value, onChange, readOnly }: ZoneComboboxProps): ReactElement {
  return (
    <input
      {...control}
      onChange={(event) => {
        onChange(event.target.value);
      }}
      readOnly={readOnly}
      type="text"
      value={value}
    />
  );
}
