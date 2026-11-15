import type { components } from "@/api/schema";

export type PlanView = components["schemas"]["PlanView"];
export type PlanState = NonNullable<PlanView["state"]>;
export type PlanGroup = components["schemas"]["PlanGroup"];
export type PlanItem = components["schemas"]["PlanItem"];
export type PlanItemsPage = components["schemas"]["PlanItemsPage"];
export type PlanCounts = components["schemas"]["PlanCounts"];
export type PlanProgress = components["schemas"]["PlanProgress"];
export type LastPlan = components["schemas"]["LastPlan"];
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
