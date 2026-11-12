import type { ReactElement } from "react";

export interface TimeFieldProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  readOnly?: boolean;
  "aria-describedby"?: string | undefined;
  "aria-invalid"?: true | undefined;
  native?: boolean;
}

export function TimeField(props: TimeFieldProps): ReactElement {
  return <div>{props.value}</div>;
}
