import type { components } from "@/api/schema";

export type ResortLatest = components["schemas"]["ResortLatest"];
export type ResortRequested = components["schemas"]["ResortRequested"];

/** What a failed sort-again request means for the page. */
export type ResortFailure = "open" | "invalid" | "rate-limited" | "failed";
