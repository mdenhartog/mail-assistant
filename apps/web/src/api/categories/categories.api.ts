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
    typeof value["mailCount"] === "number"
  );
}

function isOlder(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value["labelName"] === "string" &&
    (value["mailCount"] === null || typeof value["mailCount"] === "number")
  );
}

function isList(value: unknown): value is CategoryList {
  return (
    isRecord(value) &&
    typeof value["version"] === "number" &&
    typeof value["ready"] === "boolean" &&
    Array.isArray(value["categories"]) &&
    value["categories"].every(isCategory) &&
    Array.isArray(value["olderCategories"]) &&
    value["olderCategories"].every(isOlder) &&
    isRecord(value["other"]) &&
    typeof value["other"]["mailCount"] === "number"
  );
}

function isProblem(value: unknown): value is CategoryProblem {
  return (
    isRecord(value) &&
    typeof value["rule"] === "string" &&
    typeof value["field"] === "string" &&
    (value["index"] === null || typeof value["index"] === "number")
  );
}

async function readList(response: Response): Promise<CategoryList> {
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
  const body = error.body;
  if (error.status === 409 && isRecord(body) && isList(body["current"])) {
    return { kind: "conflict", current: body["current"] };
  }
  if (error.status === 422 && isRecord(body) && Array.isArray(body["problems"])) {
    const problems = (body["problems"] as unknown[]).filter(isProblem);
    return problems.length > 0 ? { kind: "invalid", problems } : { kind: "failed" };
  }
  return error.status === 429 ? { kind: "rate-limited" } : { kind: "failed" };
}
