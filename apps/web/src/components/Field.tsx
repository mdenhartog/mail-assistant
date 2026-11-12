import type { ReactElement, ReactNode } from "react";

export interface FieldControlProps {
  id: string;
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
}

export interface FieldProps {
  label: string;
  hint?: string;
  error?: string;
  children: (control: FieldControlProps) => ReactNode;
}

export function Field(props: FieldProps): ReactElement {
  return <div>{props.children({ id: "", "aria-describedby": undefined, "aria-invalid": undefined })}</div>;
}
