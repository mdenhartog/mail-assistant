import { clockIn, dayNote } from "@/features/settings/liveTime";

export interface Converted {
  clock: string;
  dayNote: string;
}

const CLOCK = /^([01]\d|2[0-3]):([0-5]\d)$/;

/** The zone's wall clock at a moment, read as if it were UTC; null for an unknown zone. */
function wallAsUtc(zone: string, at: Date): number | null {
  try {
    const parts: Record<string, number> = Object.fromEntries(
      new Intl.DateTimeFormat("en-GB", {
        timeZone: zone,
        hourCycle: "h23",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
        .formatToParts(at)
        .map((part) => [part.type, Number(part.value)]),
    );
    const value = Date.UTC(
      parts["year"] ?? NaN,
      (parts["month"] ?? NaN) - 1,
      parts["day"],
      parts["hour"],
      parts["minute"],
    );
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}

function offsetMs(zone: string, at: Date): number | null {
  const wall = wallAsUtc(zone, at);
  return wall === null ? null : wall - Math.floor(at.getTime() / 60_000) * 60_000;
}

/**
 * The clock time `clock` on the date it is in `from` at `at`, expressed in `to`, with a note when the
 * date there differs. Offsets are those of `at`'s date, so clock changes are respected. Null when a
 * zone or the clock is not valid.
 *
 * @example
 * convertClock("22:00", "Asia/Bangkok", "Europe/Amsterdam", new Date()); // { clock: "16:00", dayNote: "" }
 */
export function convertClock(clock: string, from: string, to: string, at: Date): Converted | null {
  const match = CLOCK.exec(clock);
  const wall = wallAsUtc(from, at);
  if (!match || wall === null) {
    return null;
  }
  const day = new Date(wall);
  const guess = Date.UTC(day.getUTCFullYear(), day.getUTCMonth(), day.getUTCDate(), Number(match[1]), Number(match[2]));
  const first = offsetMs(from, new Date(guess));
  if (first === null) {
    return null;
  }
  const second = offsetMs(from, new Date(guess - first)) ?? first;
  const instant = new Date(guess - second);
  const converted = clockIn(to, instant);
  return converted === null ? null : { clock: converted, dayNote: dayNote(to, from, instant) };
}

/** "about 1 minute", "about 5 minutes". */
export function minutesPhrase(minutes: number): string {
  return `about ${String(minutes)} ${minutes === 1 ? "minute" : "minutes"}`;
}
