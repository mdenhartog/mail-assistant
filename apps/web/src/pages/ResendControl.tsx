import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";

import { Button } from "@/components/Button";
import { useCountdown } from "@/pages/useCountdown";

export interface ResendControlProps {
  /** Epoch milliseconds until which a new code may not be asked for; null when it may be. */
  deadline: number | null;
  /** Show the seconds; false for the hourly cap, which the banner explains in minutes. */
  showSeconds: boolean;
  sending: boolean;
  /** Changes whenever the button should take focus (an expired code); null otherwise. */
  focusSignal: number | null;
  onResend: () => void;
}

const NOW_TEXT = "You can ask for a new code now.";

function waitText(seconds: number): string {
  return `You can ask for a new code in ${String(seconds)} ${seconds === 1 ? "second" : "seconds"}.`;
}

/**
 * "Send a new code" with its countdown. The visible text follows the clock but is not live; a separate
 * visually hidden polite status changes only at the start and at the end, so it is not read every second.
 * The countdown is text only, with no motion.
 *
 * @example
 * <ResendControl deadline={deadline} focusSignal={null} onResend={resend} sending={false} showSeconds />
 */
export function ResendControl({ deadline, showSeconds, sending, focusSignal, onResend }: ResendControlProps): ReactElement {
  const secondsLeft = useCountdown(deadline);
  const [start, setStart] = useState({ deadline, seconds: secondsLeft });
  const root = useRef<HTMLDivElement>(null);
  if (start.deadline !== deadline) {
    setStart({ deadline, seconds: secondsLeft });
  }
  useEffect(() => {
    if (focusSignal !== null) {
      root.current?.querySelector("button")?.focus();
    }
  }, [focusSignal]);

  const waiting = secondsLeft > 0;
  const visible = waiting ? (showSeconds ? waitText(secondsLeft) : "") : NOW_TEXT;
  const announced = waiting ? (showSeconds ? waitText(start.seconds) : "") : NOW_TEXT;
  return (
    <div className="flex flex-wrap items-center gap-3" ref={root}>
      <Button disabled={waiting} loading={sending} loadingLabel="Sending..." onClick={onResend} variant="secondary">
        Send a new code
      </Button>
      <p aria-live="off" className="text-sm text-text-muted">
        {visible}
      </p>
      <div className="sr-only" role="status">
        {announced}
      </div>
    </div>
  );
}
