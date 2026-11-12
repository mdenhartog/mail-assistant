/** A non-2xx answer from the API; carries the status only, never the body. */
export class ApiError extends Error {
  public constructor(public readonly status: number, public readonly body?: unknown) {
    super(`HTTP ${String(status)}`);
  }
}

export interface ApiOptions {
  /** Tell listeners about a 401. The first session lookup turns this off: no session yet is normal. */
  notifyUnauthorized?: boolean;
}

type RefusalListener = (status: 401 | 403) => void;

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const listeners = new Set<RefusalListener>();

// The CSRF token lives in this module variable only: no storage, no cookie, no URL (AC-8, W-4).
let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

export function hasCsrfToken(): boolean {
  return csrfToken !== null;
}

/**
 * Listen for 401 and 403 answers of any request, also background refetches.
 *
 * @returns A function that removes the listener.
 */
export function onApiRefusal(listener: RefusalListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function notify(status: number, options: ApiOptions): void {
  if (status === 403 || (status === 401 && options.notifyUnauthorized !== false)) {
    listeners.forEach((listener) => {
      listener(status === 401 ? 401 : 403);
    });
  }
}

function buildHeaders(method: string, init: RequestInit): Headers {
  const headers = new Headers(init.headers);
  if (!SAFE_METHODS.has(method) && csrfToken !== null) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  if (typeof init.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return headers;
}

/**
 * Same-origin request. Writes carry `X-CSRF-Token`; reads never do. Nothing is retried.
 *
 * @throws ApiError for any non-2xx answer.
 *
 * @example
 * await apiFetch("/auth/logout", { method: "POST" });
 */
export async function apiFetch(path: string, init: RequestInit = {}, options: ApiOptions = {}): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const response = await fetch(path, { ...init, method, headers: buildHeaders(method, init), credentials: "same-origin" });
  if (!response.ok) {
    notify(response.status, options);
    throw new ApiError(response.status);
  }
  return response;
}
