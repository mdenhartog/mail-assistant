import { vi } from "vitest";

import { INVOICES, NEWS, json } from "@/test/categories";

/** Fixtures and a stubbed `fetch` for the Review moves tests. */
export const OTHER_ID = "00000000-0000-0000-0000-000000000000";
export const PLAN_ID = "5b0c1c2e-1b1e-4c52-9d0e-0a6a1b1c00aa";
export const GONE_ID = "9a9a9a9a-1b1e-4c52-9d0e-0a6a1b1c00ff";

export const READY = {
  id: PLAN_ID,
  state: "ready",
  progress: { checked: 900, cap: 5000, unclear: 0, estimate: 2000, notLookedAt: 0 },
  groups: [
    { from: OTHER_ID, to: INVOICES.id, count: 80, approved: 0 },
    { from: NEWS.id, to: INVOICES.id, count: 2, approved: 0 },
  ],
  counts: { items: 82, pending: 82, approved: 0, rejected: 0 },
  applyAfter: null,
  lastPlan: null,
};

export const NO_PLAN = {
  ...READY,
  id: null,
  state: null,
  groups: [],
  counts: { items: 0, pending: 0, approved: 0, rejected: 0 },
};

export interface ItemRow {
  id: number;
  senderName: string;
  senderAddress: string;
  subject: string;
  from: string;
  to: string;
  decision: "pending" | "approved" | "rejected";
  state: "pending" | "approved" | "rejected" | "applied" | "skipped" | "failed";
  reason: string | null;
}

export function item(id: number, patch: Partial<ItemRow> = {}): ItemRow {
  return {
    id,
    senderName: `Sender ${String(id)}`,
    senderAddress: `sender${String(id)}@example.com`,
    subject: `Subject ${String(id)}`,
    from: OTHER_ID,
    to: INVOICES.id,
    decision: "pending",
    state: "pending",
    reason: null,
    ...patch,
  };
}

export function itemsPage(first: number, size: number, hasMore: boolean, page = 1): unknown {
  return { items: Array.from({ length: size }, (_, index) => item(first + index)), page, hasMore };
}

export interface Seen {
  method: string;
  path: string;
  search: URLSearchParams;
  body: unknown;
  token: string | null;
}

export type Answer = Response | Promise<Response>;
export interface PlanWiring {
  plan?: () => Answer;
  items?: (search: URLSearchParams) => Answer;
  decisions?: (body: unknown) => Answer;
  approve?: (body: unknown) => Answer;
  moveBack?: (planId: string) => Answer;
  categories?: () => Answer;
}

const CATEGORY_LIST = {
  version: 3,
  ready: true,
  categories: [INVOICES, NEWS],
  other: { mailCount: 7 },
  olderCategories: [],
};

function route(wiring: PlanWiring, url: URL, body: unknown): Answer {
  const table: Record<string, () => Answer> = {
    "/api/categories": () => (wiring.categories ? wiring.categories() : json(CATEGORY_LIST)),
    "/api/plan": () => (wiring.plan ? wiring.plan() : json(READY)),
    "/api/plan/items": () => (wiring.items ? wiring.items(url.searchParams) : json(itemsPage(1, 3, false))),
    "/api/plan/decisions": () => (wiring.decisions ? wiring.decisions(body) : json({ changed: 1 })),
    "/api/plan/approve": () =>
      wiring.approve ? wiring.approve(body) : json({ state: "scheduled", applyAfter: "2026-11-15T14:20:00Z" }),
  };
  const moveBack = /^\/api\/plan\/([^/]+)\/move-back$/.exec(url.pathname);
  if (moveBack) {
    const id = moveBack[1] ?? "";
    return wiring.moveBack ? wiring.moveBack(id) : json({ planId: id, processed: false });
  }
  return table[url.pathname]?.() ?? json({}, 599);
}

/** Stubs `fetch` for the plan routes and the category list; every call is recorded. */
export function wirePlan(wiring: PlanWiring = {}): Seen[] {
  const seen: Seen[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const request = new Request(new URL(input, "http://localhost"), init);
      const url = new URL(request.url);
      const body: unknown = request.method === "POST" ? await request.json().catch(() => null) : null;
      seen.push({
        method: request.method,
        path: url.pathname,
        search: url.searchParams,
        body,
        token: request.headers.get("X-CSRF-Token"),
      });
      return route(wiring, url, body);
    }),
  );
  return seen;
}
