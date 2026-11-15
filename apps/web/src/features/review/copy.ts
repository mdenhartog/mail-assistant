import { countText } from "@/features/categories/copy";

export { countText };

const CLOCK = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });

/** "14:20" in the reader's own time zone; an unreadable value gives null. */
export function clockText(iso: string | null): string | null {
  if (iso === null) {
    return null;
  }
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : CLOCK.format(date);
}

/** The button of the sticky bar says what it does and that only labels change. */
export function moveLabel(count: number): string {
  return `Move ${countText(count)}, labels only`;
}

export const DECISION_TEXT = {
  approved: "Will move",
  rejected: "Stays in place",
  pending: "Not decided yet",
} as const;
