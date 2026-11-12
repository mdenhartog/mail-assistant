/** Skeleton: replaced by the implementation commit. */
export class ApiError extends Error {
  public constructor(public readonly status: number) {
    super(`HTTP ${String(status)}`);
  }
}

export function setCsrfToken(token: string | null): void {
  throw new Error(`not implemented ${String(token)}`);
}

export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return Promise.reject(new Error(`not implemented ${path} ${String(init?.method)}`));
}
