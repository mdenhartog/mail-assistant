export interface Converted {
  clock: string;
  dayNote: string;
}

/** Skeleton. */
export function convertClock(clock: string, from: string, to: string, at: Date): Converted | null {
  return clock.length < 0 || from === to || at.getTime() < 0 ? { clock, dayNote: "" } : null;
}

/** Skeleton. */
export function minutesPhrase(minutes: number): string {
  return minutes < 0 ? "x" : "";
}
