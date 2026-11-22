import { ApiError, apiFetch } from "@/api/client";
import { readList } from "@/api/categories/categories.api";
import type { CategoryList } from "@/api/categories/categories.types";
import type { FileFailure, UploadPreview, UploadProblem } from "@/api/categories/upload.types";

/** Bigger than any file the API accepts (256 KiB), so only a file that could never pass is stopped before it is sent. */
const MAX_SEND_BYTES = 1024 * 1024;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isProblem(value: unknown): value is UploadProblem {
  return (
    isRecord(value) &&
    typeof value["rule"] === "string" &&
    typeof value["line"] === "number" &&
    typeof value["field"] === "string" &&
    typeof value["message"] === "string"
  );
}

function isCounts(value: Record<string, unknown>): boolean {
  return typeof value["added"] === "number" && typeof value["changed"] === "number" && typeof value["removed"] === "number";
}

function isPreview(value: unknown): value is UploadPreview {
  return (
    isRecord(value) &&
    typeof value["previewId"] === "string" &&
    typeof value["fileHash"] === "string" &&
    isCounts(value) &&
    typeof value["instructionsChanged"] === "boolean" &&
    Array.isArray(value["removedCategories"]) &&
    (value["removedCategories"] as unknown[]).every((name) => typeof name === "string")
  );
}

/** Sends the file for a check, its bytes unchanged so the API sees any BOM or invalid UTF-8; nothing is stored but the preview. */
export async function uploadFile(file: File): Promise<UploadPreview> {
  if (file.size > MAX_SEND_BYTES) {
    throw new ApiError(413);
  }
  const response = await apiFetch("/api/categories/upload", {
    method: "POST",
    body: file,
    headers: { "Content-Type": "application/yaml" },
  });
  const body: unknown = await response.json();
  if (!isPreview(body)) {
    throw new Error("Unexpected upload answer");
  }
  return body;
}

export async function confirmUpload(input: { previewId: string; fileHash: string }): Promise<CategoryList> {
  return readList(
    await apiFetch(`/api/categories/upload/${encodeURIComponent(input.previewId)}/confirm`, {
      method: "POST",
      body: JSON.stringify({ fileHash: input.fileHash }),
    }),
  );
}

/** `version` is the version the page shows as the current one; the API refuses when it moved on. */
export async function restorePrevious(version: number): Promise<CategoryList> {
  return readList(await apiFetch("/api/categories/restore-previous", { method: "POST", body: JSON.stringify({ version }) }));
}

export async function fetchExport(): Promise<string> {
  return (await apiFetch("/api/categories/export")).text();
}

const BY_STATUS: Record<number, FileFailure> = {
  409: { kind: "conflict" },
  413: { kind: "too-large" },
  415: { kind: "not-yaml" },
  429: { kind: "rate-limited" },
};

function problemsOf(body: unknown): UploadProblem[] {
  const list = isRecord(body) ? body["problems"] : null;
  return Array.isArray(list) ? (list as unknown[]).filter(isProblem) : [];
}

/** Tells a 422 with problems, a 409, a 413, a 415, a 429 and any other failure apart. */
export function classifyFileError(error: unknown): FileFailure {
  if (!(error instanceof ApiError)) {
    return { kind: "failed" };
  }
  if (error.status === 422) {
    const problems = problemsOf(error.body);
    return problems.length > 0 ? { kind: "invalid", problems } : { kind: "failed" };
  }
  return BY_STATUS[error.status] ?? { kind: "failed" };
}
