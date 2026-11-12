import { useEffect, useState } from "react";

import { useClock } from "@/pages/clock";

/**
 * Whole seconds left until a deadline (epoch milliseconds), read from the injected clock once a
 * second; 0 when there is no deadline or it has passed.
 *
 * @example
 * const secondsLeft = useCountdown(deadline);
 */
export function useCountdown(deadline: number | null): number {
  const clock = useClock();
  const read = (): number => (deadline === null ? 0 : Math.max(0, Math.ceil((deadline - clock.now()) / 1000)));
  const [, setTick] = useState(0);
  const secondsLeft = read();
  const running = secondsLeft > 0;

  useEffect(() => {
    if (!running) {
      return undefined;
    }
    const timer = setInterval(() => {
      setTick((tick) => tick + 1);
    }, 1000);
    return () => {
      clearInterval(timer);
    };
  }, [running, deadline]);

  return secondsLeft;
}
