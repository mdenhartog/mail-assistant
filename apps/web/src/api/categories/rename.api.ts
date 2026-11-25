import { ApiError, apiFetch } from "@/api/client";
import type { DeletedLabels, RenameConfirmation, RenameFailure, RenameItem, RenamePreview } from "@/api/categories/rename.types";

const STATES = new Set(["none", "pending", "confirmed", "done"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isItem(value: unknown): value is RenameItem {
  return (
    isRecord(value) &&
    typeof value["id"] === "string" &&
    typeof value["oldName"] === "string" &&
    typeof value["newName"] === "string" &&
    typeof value["mailCount"] === "number" &&
    (value["action"] === "rename" || value["action"] === "merge") &&
    typeof value["itemState"] === "string"
  );
}

function isSummary(value: unknown): boolean {
  return isRecord(value) && typeof value["labels"] === "number" && typeof value["mails"] === "number";
}

function isPreview(value: unknown): value is RenamePreview {
  if (!isRecord(value) || typeof value["state"] !== "string" || !STATES.has(value["state"])) {
    return false;
  }
  const hash = value["planHash"];
  return (hash === null || typeof hash === "string") && Array.isArray(value["items"]) && value["items"].every(isItem) && isSummary(value["summary"]);
}

function isDeleted(value: unknown): value is DeletedLabels {
  return (
    isRecord(value) &&
    typeof value["retentionDays"] === "number" &&
    Array.isArray(value["items"]) &&
    value["items"].every((entry) => isRecord(entry) && typeof entry["name"] === "string" && typeof entry["deletedAt"] === "string")
  );
}

/** The rename plan with its state; nothing is changed by reading it. */
export async function fetchRenamePreview(): Promise<RenamePreview> {
  const body: unknown = await (await apiFetch("/api/label-rename")).json();
  if (!isPreview(body)) {
    throw new Error("Unexpected rename answer");
  }
  return body;
}

/** The labels the agent deleted within the retention period, newest first. */
export async function fetchDeletedLabels(): Promise<DeletedLabels> {
  const body: unknown = await (await apiFetch("/api/label-rename/deleted")).json();
  if (!isDeleted(body)) {
    throw new Error("Unexpected deleted-labels answer");
  }
  return body;
}

/** Confirms the plan that was shown, with the ids the user skips. Returns the confirmation id. */
export async function postRenameConfirmation(confirmation: RenameConfirmation): Promise<string> {
  const response = await apiFetch("/api/label-rename/confirmation", { method: "POST", body: JSON.stringify(confirmation) });
  const body: unknown = await response.json();
  if (!isRecord(body) || typeof body["confirmationId"] !== "string") {
    throw new Error("Unexpected confirmation answer");
  }
  return body["confirmationId"];
}

/** Asks the agent to restore the old names. Returns the request id. */
export async function postRenameRestore(): Promise<string> {
  const response = await apiFetch("/api/label-rename/restore", { method: "POST" });
  const body: unknown = await response.json();
  if (!isRecord(body) || typeof body["requestId"] !== "string") {
    throw new Error("Unexpected restore answer");
  }
  return body["requestId"];
}

/** Tells a 401 (the session ended), a 409 (a wrong, stale or replayed plan, or nothing to restore) and a 422 apart. */
export function classifyRenameError(error: unknown, context: "confirm" | "restore"): RenameFailure {
  if (!(error instanceof ApiError)) {
    return "failed";
  }
  switch (error.status) {
    case 401:
      return "session";
    case 409:
      return context === "confirm" ? "changed" : "nothing-to-restore";
    case 422:
      return "unknown-skip";
    default:
      return "failed";
  }
}
