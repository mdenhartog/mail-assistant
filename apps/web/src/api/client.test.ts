import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "@/api/client";

function answer(status: number, body: string): void {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(body, { status }))));
}

async function failure(): Promise<ApiError> {
  const error: unknown = await apiFetch("/api/settings", { method: "PUT", body: "{}" }).catch((e: unknown) => e);
  if (!(error instanceof ApiError)) {
    throw new Error("expected an ApiError");
  }
  return error;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ApiError body", () => {
  it.each([409, 422])("given a %i with a JSON body, when thrown, then the parsed body is on the error", async (status) => {
    answer(status, JSON.stringify({ problems: [] }));

    const error = await failure();

    expect(error.status).toBe(status);
    expect(error.body).toEqual({ problems: [] });
  });

  it("given a 500 with a JSON body, when thrown, then the message is the status only and never the body", async () => {
    answer(500, JSON.stringify({ secret: "stack trace" }));

    const error = await failure();

    expect(error.message).toBe("HTTP 500");
    expect(error.message).not.toContain("stack trace");
  });

  it("given a 422 whose body is not JSON, when thrown, then the body is null", async () => {
    answer(422, "<html>nope</html>");

    expect((await failure()).body).toBeNull();
  });
});
