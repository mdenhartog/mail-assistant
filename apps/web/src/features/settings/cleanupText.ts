import type { NumberKey, Ranges } from "@/features/settings/useSettings";

/** "1 day", "7 days". */
function plural(count: number, unit: string): string {
  return `${String(count)} ${unit}${count === 1 ? "" : "s"}`;
}

/** "12 hours", "5 minutes", "2 hours 30 minutes", "12 hours 1 minute". */
export function durationText(minutes: number): string {
  const parts = [];
  if (minutes >= 60) {
    parts.push(plural(Math.floor(minutes / 60), "hour"));
  }
  if (minutes % 60 > 0 || minutes < 60) {
    parts.push(plural(minutes % 60, "minute"));
  }
  return parts.join(" ");
}

/** A value of one cleanup number in words: minutes as a duration, the others as days. */
export function valueText(field: NumberKey, value: number): string {
  return field === "waitingMinutes" ? durationText(value) : plural(value, "day");
}

function spanText(field: NumberKey, ranges: Ranges): string {
  const { min, max } = ranges[field];
  const low = field === "waitingMinutes" ? durationText(min) : String(min);
  return `${low} to ${valueText(field, max)}`;
}

/** What the tile says under the field: "1 to 30 days, default 7 days". */
export function rangeText(field: NumberKey, ranges: Ranges): string {
  return `${spanText(field, ranges)}, default ${valueText(field, ranges[field].default)}`;
}

const SUBJECT: Record<NumberKey, string> = {
  waitingMinutes: "The waiting time",
  protectionDays: "The protection period",
  retentionDays: "The retention",
};

/** The inline message for a number outside its range, in the words of the help text. */
export function rangeMessage(field: NumberKey, ranges: Ranges): string {
  return `${SUBJECT[field]} can be ${spanText(field, ranges)}. The default is ${valueText(field, ranges[field].default)}.`;
}
