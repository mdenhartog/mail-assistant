import { ApiError, apiFetch } from "@/api/client";
import type {
  ApprovalResult,
  ApproveBody,
  DecisionBody,
  DecisionResult,
  GroupRef,
  MoveBackResult,
  PlanFailure,
  PlanItemsPage,
  PlanView,
} from "@/api/plan/plan.types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isNumberAt(value: Record<string, unknown>, ...keys: string[]): boolean {
  return keys.every((key) => typeof value[key] === "number");
}

function allOf(value: unknown, check: (item: unknown) => boolean): boolean {
  return Array.isArray(value) && (value as unknown[]).every(check);
}

function isExample(value: unknown): boolean {
  return isRecord(value) && ["senderName", "senderAddress", "subject"].every((key) => typeof value[key] === "string");
}

function isGroup(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value["from"] === "string" &&
    typeof value["to"] === "string" &&
    isNumberAt(value, "count", "approved", "rejected") &&
    isExample(value["example"])
  );
}

function isStringOrNull(value: unknown): boolean {
  return value === null || typeof value === "string";
}

function isNumberOrNull(value: unknown): boolean {
  return value === null || typeof value === "number";
}

const LAST_STATES = ["applied", "cancelled", "replaced"];

function isMovedCount(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isLastPlan(value: unknown): boolean {
  return (
    value === null ||
    (isRecord(value) &&
      typeof value["id"] === "string" &&
      LAST_STATES.includes(String(value["state"])) &&
      isStringOrNull(value["endedAt"]) &&
      isMovedCount(value["movedCount"]))
  );
}

function isProgress(value: unknown): boolean {
  return isRecord(value) && isNumberAt(value, "checked", "cap", "unclear");
}

function isCounts(value: unknown): boolean {
  return isRecord(value) && isNumberAt(value, "items", "pending", "approved", "rejected");
}

function hasApplySettings(value: Record<string, unknown>): boolean {
  return isNumberOrNull(value["applyThreshold"]) && isNumberOrNull(value["applyDelayMinutes"]) && isLastPlan(value["lastPlan"]);
}

function isPlan(value: unknown): value is PlanView {
  return (
    isRecord(value) &&
    (value["state"] === null || typeof value["state"] === "string") &&
    isProgress(value["progress"]) &&
    isCounts(value["counts"]) &&
    hasApplySettings(value) &&
    allOf(value["groups"], isGroup)
  );
}

function isItem(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNumberAt(value, "id") &&
    ["senderName", "senderAddress", "subject", "from", "to", "decision", "state"].every((key) => typeof value[key] === "string")
  );
}

function isItemsPage(value: unknown): value is PlanItemsPage {
  return isRecord(value) && typeof value["hasMore"] === "boolean" && isNumberAt(value, "page") && allOf(value["items"], isItem);
}

async function read<T>(response: Response, guard: (body: unknown) => body is T, what: string): Promise<T> {
  const body: unknown = await response.json();
  if (!guard(body)) {
    throw new Error(`Unexpected ${what} answer`);
  }
  return body;
}

function post(path: string, body?: unknown): Promise<Response> {
  return apiFetch(path, { method: "POST", ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
}

export async function fetchPlan(): Promise<PlanView> {
  return read(await apiFetch("/api/plan"), isPlan, "plan");
}

/** One page of the items of a group, or of the whole plan when `group` is null. Only ids and the page number are sent. */
export async function fetchPlanItems(group: GroupRef | null, page: number): Promise<PlanItemsPage> {
  const query = new URLSearchParams(group ? { from: group.from, to: group.to } : {});
  query.set("page", String(page));
  return read(await apiFetch(`/api/plan/items?${query.toString()}`), isItemsPage, "items");
}

export async function postDecision(body: DecisionBody): Promise<DecisionResult> {
  const answer: unknown = await (await post("/api/plan/decisions", body)).json();
  if (!isRecord(answer) || typeof answer["changed"] !== "number") {
    throw new Error("Unexpected decision answer");
  }
  return { changed: answer["changed"] };
}

export async function approvePlan(body: ApproveBody): Promise<ApprovalResult> {
  const guard = (value: unknown): value is ApprovalResult => isRecord(value) && typeof value["state"] === "string";
  return read(await post("/api/plan/approve", body), guard, "approval");
}

export async function moveBack(planId: string): Promise<MoveBackResult> {
  const guard = (value: unknown): value is MoveBackResult => isRecord(value) && typeof value["processed"] === "boolean";
  return read(await post(`/api/plan/${encodeURIComponent(planId)}/move-back`), guard, "move back");
}

/** Tells a 409 (the plan changed), a 422 for too many ids, a 429 and any other failure apart. */
export function classifyPlanError(error: unknown): PlanFailure {
  if (!(error instanceof ApiError)) {
    return { kind: "failed" };
  }
  if (error.status === 409) {
    return { kind: "conflict" };
  }
  if (error.status === 422 && isRecord(error.body) && error.body["reason"] === "too_many_ids") {
    return { kind: "too-many-ids" };
  }
  return error.status === 429 ? { kind: "rate-limited" } : { kind: "failed" };
}
