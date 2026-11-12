import type { ReactElement } from "react";

export interface ResendControlProps {
  /** Epoch milliseconds until which a new code may not be asked for; null when it may be. */
  deadline: number | null;
  /** Show the seconds; false for the hourly cap, which the banner explains in minutes. */
  showSeconds: boolean;
  sending: boolean;
  onResend: () => void;
}

/**
 * "Send a new code" with its countdown text and the hidden status for the start and end.
 *
 * @example
 * <ResendControl deadline={deadline} onResend={resend} sending={false} showSeconds />
 */
export function ResendControl(): ReactElement | null {
  return null;
}
