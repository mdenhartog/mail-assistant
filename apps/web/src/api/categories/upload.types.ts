import type { components } from "@/api/schema";

export type UploadPreview = components["schemas"]["UploadPreview"];
export type UploadProblem = components["schemas"]["UploadProblem"];

/** What a failed upload, confirm or restore means for the page. */
export type FileFailure =
  | { kind: "invalid"; problems: UploadProblem[] }
  | { kind: "conflict" }
  | { kind: "too-large" }
  | { kind: "not-yaml" }
  | { kind: "rate-limited" }
  | { kind: "failed" };
