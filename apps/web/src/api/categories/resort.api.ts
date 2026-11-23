import { ApiError, apiFetch } from "@/api/client";
import type { ResortFailure, ResortLatest, ResortRequested } from "@/api/categories/resort.types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** The threshold the field shows: 50 on the first visit, else the latest request's. */
export async function fetchLatestThreshold(): Promise<ResortLatest> {
  const body: unknown = await (await apiFetch("/api/resort-requests/latest")).json();
  if (!isRecord(body) || typeof body["threshold"] !== "number") {
    throw new Error("Unexpected resort answer");
  }
  return { threshold: body["threshold"] };
}

/** Asks the agent to sort the mail again; `threshold` is a whole number from 50 to 100. */
export async function postResort(threshold: number): Promise<ResortRequested> {
  const response = await apiFetch("/api/resort-requests", { method: "POST", body: JSON.stringify({ threshold }) });
  const body: unknown = await response.json();
  if (!isRecord(body) || typeof body["requestId"] !== "string" || typeof body["threshold"] !== "number") {
    throw new Error("Unexpected resort answer");
  }
  return { requestId: body["requestId"], threshold: body["threshold"] };
}

/** Tells a 409 (a plan is open or the last request is not a plan yet), a 422, a 429 and any other failure apart. */
export function classifyResortError(error: unknown): ResortFailure {
  if (!(error instanceof ApiError)) {
    return "failed";
  }
  switch (error.status) {
    case 409:
      return "open";
    case 422:
      return "invalid";
    case 429:
      return "rate-limited";
    default:
      return "failed";
  }
}
