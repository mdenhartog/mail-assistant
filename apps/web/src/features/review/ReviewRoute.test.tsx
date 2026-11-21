import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, routes } from "@/App";
import { setCsrfToken } from "@/api/client";
import { json } from "@/test/categories";
import { READY } from "@/test/plan";

const SESSION = {
  maskedAddress: "m***@example.com",
  csrfToken: "csrf-secret-4711",
  idleExpiresAt: "2026-11-12T12:00:00Z",
  absoluteExpiresAt: "2026-11-12T23:00:00Z",
  noticeIntervalMinutes: 5,
};

/** `ended` turns the session into a 401 too, as it is on the server once the session has ended. */
function stub(plan: (request: Request) => Response, ended: { value: boolean } = { value: false }): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string, init?: RequestInit) => {
      const request = new Request(new URL(input, "http://localhost"), init);
      const path = new URL(request.url).pathname;
      if (path === "/api/session") {
        return Promise.resolve(ended.value ? new Response(null, { status: 401 }) : json(SESSION));
      }
      if (path === "/api/categories") {
        return Promise.resolve(json({ version: 1, ready: true, generalInstructions: "", categories: [], other: { mailCount: 0 }, olderCategories: [] }));
      }
      return Promise.resolve(plan(request));
    }),
  );
}

function open(path: string): ReturnType<typeof createMemoryRouter> {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<App queryClient={client} router={router} />);
  return router;
}

afterEach(() => {
  setCsrfToken(null);
  vi.unstubAllGlobals();
});

describe("the /review route", () => {
  it("shows the page inside the signed-in frame with the navigation marking Review moves", async () => {
    stub(() => json({ ...READY, groups: [] }));
    open("/review");

    expect(await screen.findByRole("heading", { level: 1, name: "Review moves" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Review moves" })).toHaveAttribute("aria-current", "page");
  });

  it("given an expired session (401), then the sign-in page shows with the session notice", async () => {
    const ended = { value: false };
    stub(() => {
      ended.value = true;
      return new Response(null, { status: 401 });
    }, ended);
    const router = open("/review");

    expect(await screen.findByText("Your session ended.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
  });

  it("given the lock (403) on a decision, then the refusal page replaces the app and no mail stays in the DOM", async () => {
    stub((request) => (request.method === "GET" ? json(READY) : new Response(null, { status: 403 })));
    open("/review");
    const approve = await screen.findAllByRole("button", { name: /^Approve group/ });
    await userEvent.click(approve[0] as HTMLElement);

    expect(await screen.findByRole("heading", { name: "Access refused" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Mails that would move" })).not.toBeInTheDocument();
    });
  });
});
