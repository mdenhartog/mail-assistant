import { QueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, routes } from "@/App";
import { setCsrfToken } from "@/api/client";
import { expectNoAxeViolations } from "@/test/axe";
import { json } from "@/test/categories";
import { READY } from "@/test/plan";
import { CLEANUP, RANGES } from "@/test/settings";

const SESSION = {
  maskedAddress: "m***@example.com",
  csrfToken: "csrf-secret-4711",
  idleExpiresAt: "2026-11-12T12:00:00Z",
  absoluteExpiresAt: "2026-11-12T23:00:00Z",
  noticeIntervalMinutes: 5,
};
const SETTINGS = {
  values: { timeZone: "Europe/Amsterdam", quietStart: "23:00", quietEnd: "07:00", overviewAt: "18:00", remindAt: "09:00", ...CLEANUP },
  ranges: RANGES,
  version: 1,
  updatedAt: null,
  updatedVia: null,
};

function stubApp(plan: () => Response): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string) => {
      const path = new URL(input, "http://localhost").pathname;
      if (path === "/api/session") {
        return Promise.resolve(json(SESSION));
      }
      if (path === "/api/plan") {
        return Promise.resolve(plan());
      }
      return Promise.resolve(path === "/api/settings" ? json(SETTINGS) : new Response(null, { status: 404 }));
    }),
  );
}

async function openSettings(): Promise<void> {
  const router = createMemoryRouter(routes, { initialEntries: ["/settings"] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<App queryClient={client} router={router} />);
  await screen.findByRole("heading", { level: 1, name: "Settings" });
}

afterEach(() => {
  setCsrfToken(null);
  vi.unstubAllGlobals();
});

describe("ProtectedShell: the open items badge (AC-23)", () => {
  it("given pending items in a ready plan, then the Review moves link shows the count on a page that is not the review", async () => {
    stubApp(() => json(READY));
    await openSettings();

    expect(await screen.findByRole("link", { name: "Review moves 82 open items" })).toBeInTheDocument();
    await expectNoAxeViolations(document.body);
  });

  it("given no pending item, then the badge is hidden", async () => {
    stubApp(() => json({ ...READY, counts: { items: 82, pending: 0, approved: 82, rejected: 0 } }));
    await openSettings();

    expect(await screen.findByRole("link", { name: "Review moves" })).toBeInTheDocument();
    expect(screen.queryByText(/open items/)).not.toBeInTheDocument();
  });

  it("given a plan that is not ready, then the badge is hidden", async () => {
    stubApp(() => json({ ...READY, state: "building", counts: { items: 5, pending: 5, approved: 0, rejected: 0 } }));
    await openSettings();

    expect(await screen.findByRole("link", { name: "Review moves" })).toBeInTheDocument();
    expect(screen.queryByText(/open items/)).not.toBeInTheDocument();
  });

  it("given the plan cannot be read, then the page still works and shows no badge", async () => {
    stubApp(() => json({}, 500));
    await openSettings();

    expect(await screen.findByRole("link", { name: "Review moves" })).toBeInTheDocument();
    expect(screen.queryByText(/open items/)).not.toBeInTheDocument();
  });
});
