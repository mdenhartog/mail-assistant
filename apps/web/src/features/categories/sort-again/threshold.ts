const MIN_THRESHOLD = 50;
const MAX_THRESHOLD = 100;

/** The reason shown for anything the api would refuse. */
export const THRESHOLD_REASON = "Use a whole number from 50 to 100.";

/** The same rule as the api: digits only, no sign, space or decimal point, from 50 to 100. `null` when it is refused. */
export function parseThreshold(text: string): number | null {
  if (!/^[0-9]{1,3}$/.test(text)) {
    return null;
  }
  const value = Number(text);
  return value >= MIN_THRESHOLD && value <= MAX_THRESHOLD ? value : null;
}
