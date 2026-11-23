import { countText } from "@/features/categories/copy";

export { countText };

const DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });
const CLOCK = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });

/** "14:20" in the reader's own time zone; an unreadable value gives null. */
export function clockText(iso: string | null): string | null {
  if (iso === null) {
    return null;
  }
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : CLOCK.format(date);
}

/** "15 Nov" in the reader's own time zone: the one date format of the review; an unreadable value gives null. */
function dayText(iso: string | null): string | null {
  if (iso === null) {
    return null;
  }
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : DAY.format(date);
}

/** " on 15 Nov at 14:20" for the end of a plan, or "" when the time is unknown, so a sentence stays true. */
export function onDayAtText(iso: string | null): string {
  const day = dayText(iso);
  const clock = clockText(iso);
  return day === null || clock === null ? "" : ` on ${day} at ${clock}`;
}

export const SKIPPED_FALLBACK = "You moved this mail yourself, so I left it alone.";
export const FAILED_FALLBACK = "Gmail did not accept the change. It stays where it was.";

/** The button of the sticky bar says what it does; the line beside it says that only labels change. */
export function moveLabel(count: number): string {
  return `Move ${countText(count)} to their new categories`;
}

export const LABELS_ONLY_HELPER = "Only labels change, nothing is deleted";

export const DECISION_TEXT = {
  approved: "Will move",
  rejected: "Stays in place",
  pending: "Not decided yet",
} as const;

export const TIP_LABEL = "This is a suggestion, nothing was changed.";

/** What the pair of a mail is: the old or new topic and extra label, as full names, or "none" when it has no such label. */
export function pairText(side: "From" | "To", topic: string | null, extra: string | null): string {
  return `${side} topic ${topic ?? "none"}, extra ${extra ?? "none"}`;
}

export function confidenceText(pct: number): string {
  return `Model confidence ${String(pct)} %`;
}

export interface AutoCounts {
  moved: number;
  scheduled: number;
  skipped: number;
}

function plural(count: number, one: string, many: string): string {
  return count === 1 ? one : many;
}

/** "5 mails were already moved on their own, 12 are scheduled and 1 was skipped."; null when all three are 0. */
export function autoText({ moved, scheduled, skipped }: AutoCounts): string | null {
  const parts = [
    { count: moved, text: plural(moved, "was already moved on its own", "were already moved on their own") },
    { count: scheduled, text: plural(scheduled, "is scheduled", "are scheduled") },
    { count: skipped, text: plural(skipped, "was skipped", "were skipped") },
  ].filter((part) => part.count > 0);
  const words = parts.map((part, index) => `${String(part.count)} ${index === 0 ? `${plural(part.count, "mail", "mails")} ` : ""}${part.text}`);
  const last = words.pop();
  if (last === undefined) {
    return null;
  }
  return `${words.length === 0 ? last : `${words.join(", ")} and ${last}`}.`;
}
