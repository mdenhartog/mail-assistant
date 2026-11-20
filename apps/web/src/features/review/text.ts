import type { CategoryItem } from "@/api/categories/categories.types";
import type { GroupRef } from "@/api/plan/plan.types";

/** The nil UUID is the built-in "Other" (contract of `PlanGroup`). */
const OTHER_ID = "00000000-0000-0000-0000-000000000000";

/**
 * Sender names, addresses and subjects are text from outside (ADR-0044). Format characters (bidi controls,
 * zero-width) and control characters are removed so a name cannot reorder or hide what is next to it (AC-44).
 * Look-alike letters are left as they are: the real address is always shown beside the name.
 */
export function cleanText(text: string): string {
  return text.replace(/[\p{Cf}\p{Cc}]/gu, "");
}

/** A category id as the reader knows it; an id that no longer resolves gets a text that is safe to show. */
export function categoryName(id: string, categories: readonly CategoryItem[]): string {
  if (id === OTHER_ID) {
    return "Other";
  }
  return categories.find((category) => category.id === id)?.name ?? "A category that no longer exists";
}

export function groupKey(group: GroupRef): string {
  return `${group.from}:${group.to}`;
}

export function groupTitle(group: GroupRef, categories: readonly CategoryItem[]): string {
  return `${categoryName(group.from, categories)} to ${categoryName(group.to, categories)}`;
}
