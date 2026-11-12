import type { ReactElement } from "react";

export interface CodeFailure {
  /** Tries left from the server's refusal, or null when it sent none. */
  attemptsLeft: number | null;
  /** Grows with every refusal so a repeated one moves focus again. */
  seq: number;
}

export interface CodeStepProps {
  maskedAddress: string;
  verifying: boolean;
  failure: CodeFailure | null;
  onSubmit: (code: string) => void;
  onUseAnotherUsername: () => void;
}

/** Step 2 of the login page. */
export function CodeStep(): ReactElement {
  return <></>;
}
