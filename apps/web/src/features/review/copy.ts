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
export function dayText(iso: string | null): string | null {
  if (iso === null) {
    return null;
  }
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : DAY.format(date);
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
