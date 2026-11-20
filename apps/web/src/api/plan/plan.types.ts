import type { components } from "@/api/schema";

export type PlanView = components["schemas"]["PlanView"];
export type PlanState = NonNullable<PlanView["state"]>;
export type PlanGroup = components["schemas"]["PlanGroup"];
export type PlanItem = components["schemas"]["PlanItem"];
export type PlanItemsPage = components["schemas"]["PlanItemsPage"];
export type ApprovalResult = components["schemas"]["ApprovalResult"];
export type DecisionResult = components["schemas"]["DecisionResult"];
export type MoveBackResult = components["schemas"]["MoveBackResult"];
export type GroupRef = components["schemas"]["GroupRef"];
export type Decision = components["schemas"]["DecisionRequest"]["decision"];

/** The generated `ids` is `unknown` (the limit has no type in the document), so the scope is typed here. */
export type DecisionScope = { group: GroupRef; groupCount: number } | { ids: number[] } | { all: true };

export interface DecisionBody {
  planId: string;
  itemCount: number;
  scope: DecisionScope;
  decision: Decision;
}

export interface ApproveBody {
  planId: string;
  itemCount: number;
}

/** What a failed plan request means for the page. */
export type PlanFailure =
  | { kind: "conflict" }
  | { kind: "too-many-ids" }
  | { kind: "rate-limited" }
  | { kind: "failed" };

/** The most ids one decision may name; more is sent as a group or in several requests. */
export const MAX_IDS = 200;

/** The sort choices of the review items; "default" keeps the order of the plan. */
export type ItemSort = "default" | "sender-asc" | "sender-desc" | "subject-asc" | "subject-desc";

/**
 * What narrows and orders the mails of a group. The sender text is personal data: it lives in memory and in the body
 * of a POST only, never in a URL, storage or a log (AC-59).
 */
export interface ItemFilter {
  sender: string;
  sort: ItemSort;
}

/** The most characters of sender text the API accepts. */
export const MAX_SENDER_LENGTH = 100;

export const NO_FILTER: ItemFilter = { sender: "", sort: "default" };

export function isFiltering(filter: ItemFilter): boolean {
  return filter.sender.trim() !== "" || filter.sort !== "default";
}
