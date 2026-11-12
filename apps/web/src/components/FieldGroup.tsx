import type { ReactElement, ReactNode } from "react";

interface GroupControlProps {
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
}

export interface FieldGroupProps {
  legend: string;
  hint?: string | undefined;
  error?: string | undefined;
  children: (control: GroupControlProps) => ReactNode;
}

export function FieldGroup({ legend }: FieldGroupProps): ReactElement {
  return <fieldset>{legend}</fieldset>;
}
