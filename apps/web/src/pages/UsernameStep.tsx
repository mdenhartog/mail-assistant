import type { ReactElement } from "react";

export interface UsernameStepProps {
  sending: boolean;
  failed: boolean;
  onSubmit: (username: string) => void;
}

/** Step 1 of the login page. */
export function UsernameStep(): ReactElement {
  return <></>;
}
