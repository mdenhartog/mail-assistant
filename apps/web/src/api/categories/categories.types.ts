import type { components } from "@/api/schema";

export type CategoryList = components["schemas"]["CategoryList"];
export type CategoryItem = components["schemas"]["CategoryItem"];
export type CategoryInput = components["schemas"]["CategoryInput"];
export type CategoryListUpdate = components["schemas"]["CategoryListUpdate"];
export type CategoryProblem = components["schemas"]["CategoryProblem"];

/** What a failed save means for the page. */
export type SaveOutcome =
  | { kind: "invalid"; problems: CategoryProblem[] }
  | { kind: "conflict"; current: CategoryList }
  | { kind: "rate-limited" }
  | { kind: "failed" };
