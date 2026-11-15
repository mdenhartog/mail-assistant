import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, routes } from "@/App";
import { setCsrfToken } from "@/api/client";
import { INVOICES, LIST, json } from "@/test/categories";

const SESSION = {
  maskedAddress: "m***@example.com",
  csrfToken: "csrf-secret-4711",
  idleExpiresAt: "2026-11-12T12:00:00Z",
  absoluteExpiresAt: "2026-11-12T23:00:00Z",
  noticeIntervalMinutes: 5,
};

type Handler = (request: Request) => Response;

function stub(categories: Handler): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string, init?: RequestInit) => {
      const request = new Request(new URL(input, "http://localhost"), init);
      const path = new URL(request.url).pathname;
      return Promise.resolve(path === "/api/session" ? json(SESSION) : categories(request));
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

describe("the /categories route", () => {
  it("shows the page inside the signed-in frame with the navigation marking Categories", async () => {
    stub(() => json(LIST));
    open("/categories");

    expect(await screen.findByDisplayValue(INVOICES.name)).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Categories" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Signed in as m***@example.com")).toBeInTheDocument();
  });

  it("given an expired session (401), then the sign-in page shows with the session notice and no list stays", async () => {
    stub(() => new Response(null, { status: 401 }));
    const router = open("/categories");

    expect(await screen.findByText("Your session ended.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(screen.queryByDisplayValue(INVOICES.name)).not.toBeInTheDocument();
  });

  it("given the lock (403) on a save, then the refusal page replaces the app and no category stays in the DOM", async () => {
    stub((request) => (request.method === "GET" ? json(LIST) : new Response(null, { status: 403 })));
    open("/categories");
    const name = await screen.findByDisplayValue(INVOICES.name);
    await userEvent.type(name, "x");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await userEvent.click(await screen.findByRole("button", { name: "Save" }));

    expect(await screen.findByRole("heading", { name: "Access refused" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByDisplayValue(`${INVOICES.name}x`)).not.toBeInTheDocument();
    });
  });
});
