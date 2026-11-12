import { ApiError, apiFetch } from "@/api/client";
import type { components } from "@/api/schema";

export type RequestCodeAnswer = components["schemas"]["RequestCodeResponse"];

function isRequestCodeAnswer(value: unknown): value is RequestCodeAnswer {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Record<string, unknown>)["maskedAddress"] === "string"
  );
}

/**
 * Asks for a sign-in code. The answer is the same for every username (ADR-0036).
 *
 * @example
 * const { maskedAddress } = await requestCode("marco");
 */
export async function requestCode(username: string): Promise<RequestCodeAnswer> {
  const response = await apiFetch("/auth/request-code", { method: "POST", body: JSON.stringify({ username }) });
  const body: unknown = await response.json();
  if (!isRequestCodeAnswer(body)) {
    throw new Error("Unexpected request-code answer");
  }
  return body;
}

/**
 * Sends the code. A 204 signs in; the page always goes to the settings, so the `X-Return-To`
 * header is not read.
 */
export async function verifyCode(code: string): Promise<void> {
  await apiFetch("/auth/verify-code", { method: "POST", body: JSON.stringify({ code }) });
}

/** Tries left from a refusal body (ADR-0038: real or decoy), or `null` when the body has none. */
export function attemptsLeftOf(error: unknown): number | null {
  if (!(error instanceof ApiError) || typeof error.body !== "object" || error.body === null) {
    return null;
  }
  const value = (error.body as Record<string, unknown>)["attemptsLeft"];
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}
