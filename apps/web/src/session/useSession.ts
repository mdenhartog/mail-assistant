import { useQuery } from "@tanstack/react-query";
import type { UseQueryResult } from "@tanstack/react-query";

import { ApiError, apiFetch, hasCsrfToken, setCsrfToken } from "@/api/client";
import type { components } from "@/api/schema";

export type SessionInfo = components["schemas"]["SessionInfo"];

/** Query key of the session; sign-in invalidates it so the new session is read. */
export const sessionKey = ["session"] as const;

function isSessionInfo(value: unknown): value is SessionInfo {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return typeof record["maskedAddress"] === "string" && typeof record["csrfToken"] === "string";
}

/** Reads the session; `null` means there is none. Keeps the CSRF token in memory only. */
async function loadSession(): Promise<SessionInfo | null> {
  try {
    const response = await apiFetch("/api/session", {}, { notifyUnauthorized: hasCsrfToken() });
    const body: unknown = await response.json();
    if (!isSessionInfo(body)) {
      throw new Error("Unexpected session answer");
    }
    setCsrfToken(body.csrfToken);
    return body;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      setCsrfToken(null);
      return null;
    }
    throw error;
  }
}

/**
 * The signed-in session, or `null` when there is none.
 *
 * @example
 * const { data: session } = useSession();
 */
export function useSession(): UseQueryResult<SessionInfo | null> {
  return useQuery({ queryKey: sessionKey, queryFn: loadSession, staleTime: 60_000 });
}
