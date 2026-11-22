import { ApiError, apiFetch } from "@/api/client";
import type { CategoryList, CategoryListUpdate, CategoryProblem, SaveOutcome } from "@/api/categories/categories.types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isCategory(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value["id"] === "string" &&
    typeof value["name"] === "string" &&
    typeof value["description"] === "string" &&
    typeof value["mailCount"] === "number" &&
    hasListFields(value)
  );
}

function hasListFields(value: Record<string, unknown>): boolean {
  return (
    (value["kind"] === "topic" || value["kind"] === "extra") &&
    typeof value["notify"] === "boolean" &&
    allOf(value["senders"], isSender)
  );
}

function isIndex(value: unknown): boolean {
  return value === null || typeof value === "number";
}

function isSender(value: unknown): boolean {
  return isRecord(value) && typeof value["entry"] === "string" && typeof value["subdomains"] === "boolean";
}

function isOlder(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value["labelName"] === "string" &&
    (value["mailCount"] === null || typeof value["mailCount"] === "number")
  );
}

function allOf(value: unknown, check: (item: unknown) => boolean): boolean {
  return Array.isArray(value) && (value as unknown[]).every(check);
}

function isOther(value: unknown): boolean {
  return isRecord(value) && typeof value["mailCount"] === "number";
}

function isList(value: unknown): value is CategoryList {
  return (
    isRecord(value) &&
    typeof value["version"] === "number" &&
    typeof value["ready"] === "boolean" &&
    typeof value["generalInstructions"] === "string" &&
    allOf(value["categories"], isCategory) &&
    allOf(value["olderCategories"], isOlder) &&
    isOther(value["other"])
  );
}

function isProblem(value: unknown): value is CategoryProblem {
  return (
    isRecord(value) &&
    typeof value["rule"] === "string" &&
    typeof value["field"] === "string" &&
    isIndex(value["index"]) &&
    isIndex(value["position"]) &&
    isIndex(value["otherIndex"])
  );
}

function problemsOf(body: Record<string, unknown>): CategoryProblem[] {
  return Array.isArray(body["problems"]) ? (body["problems"] as unknown[]).filter(isProblem) : [];
}

export async function readList(response: Response): Promise<CategoryList> {
  const body: unknown = await response.json();
  if (!isList(body)) {
    throw new Error("Unexpected categories answer");
  }
  return body;
}

export async function fetchCategories(): Promise<CategoryList> {
  return readList(await apiFetch("/api/categories"));
}

export async function putCategories(update: CategoryListUpdate): Promise<CategoryList> {
  return readList(await apiFetch("/api/categories", { method: "PUT", body: JSON.stringify(update) }));
}

/** Tells a 422 with problems, a 409 with the current list, a 429 and any other failure apart. */
export function classifySaveError(error: unknown): SaveOutcome {
  if (!(error instanceof ApiError)) {
    return { kind: "failed" };
  }
  const body = isRecord(error.body) ? error.body : {};
  if (error.status === 409 && isList(body["current"])) {
    return { kind: "conflict", current: body["current"] };
  }
  if (error.status === 422) {
    const problems = problemsOf(body);
    return problems.length > 0 ? { kind: "invalid", problems } : { kind: "failed" };
  }
  return error.status === 429 ? { kind: "rate-limited" } : { kind: "failed" };
}
