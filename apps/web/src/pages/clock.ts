import { createContext, useContext } from "react";

/** The browser's source of time; injected so tests move it by hand. */
export interface Clock {
  /** Milliseconds since the epoch. */
  now: () => number;
}

export const systemClock: Clock = { now: () => Date.now() };

export const ClockContext = createContext<Clock>(systemClock);

/**
 * The clock of the page: the system clock unless the app was given another one.
 *
 * @example
 * const clock = useClock();
 */
export function useClock(): Clock {
  return useContext(ClockContext);
}
