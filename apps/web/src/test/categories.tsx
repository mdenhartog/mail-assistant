import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";

import { CategoriesPage } from "@/features/categories/CategoriesPage";

/** Fixtures and a stubbed `fetch` for the Categories page tests. */
export const INVOICES = {
  id: "7f0c1c2e-1b1e-4c52-9d0e-0a6a1b1c0001",
  name: "Invoices",
  description: "Invoices, receipts and payment confirmations.",
  mailCount: 12,
  kind: "extra" as const,
  notify: true,
  senders: [{ entry: "billing@example.com", subdomains: false, skippedCount: 0 }],
};
export const NEWS = {
  id: "7f0c1c2e-1b1e-4c52-9d0e-0a6a1b1c0002",
  name: "Newsletters",
  description: "Weekly digests I read on Sunday.",
  mailCount: 1,
  kind: "topic" as const,
  notify: false,
  senders: [] as { entry: string; subdomains: boolean; skippedCount: number }[],
};

export const LIST = {
  version: 3,
  archiveLabel: "Archive",
  ready: true,
  generalInstructions: "Keep receipts for the tax year.",
  categories: [INVOICES, NEWS],
  other: { mailCount: 7 },
  olderCategories: [{ labelName: "Travel", mailCount: null }],
};

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

interface Put {
  body: {
    version: number;
    generalInstructions: string;
    archiveLabel: string;
    categories: {
      id?: string;
      name: string;
      description: string;
      kind: "topic" | "extra";
      notify: boolean;
      senders: { entry: string; subdomains: boolean }[];
    }[];
  };
  token: string | null;
}

type Answer = Response | Promise<Response>;

/** What `GET /api/plan` says while no plan is open. */
export const NO_OPEN_PLAN = {
  id: null,
  state: null,
  progress: { checked: 0, cap: 5000, unclear: 0, estimate: 0, notLookedAt: 0 },
  groups: [],
  counts: { items: 0, pending: 0, approved: 0, rejected: 0 },
  applyAfter: null,
  applyThreshold: null,
  applyDelayMinutes: null,
  lastPlan: null,
};

export interface WireOptions {
  get?: () => Answer;
  put?: (body: Put["body"]) => Answer;
  /** `GET /api/resort-requests/latest` (default: the first visit, 50). */
  latest?: () => Answer;
  /** `GET /api/plan` (default: no plan open). */
  plan?: () => Answer;
  /** `POST /api/resort-requests` (default: stored, 201). */
  resort?: (body: unknown) => Answer;
}

export interface Wired {
  puts: Put[];
  gets: () => number;
  /** The bodies of every POST to `/api/resort-requests`. */
  resorts: unknown[];
}

type Seen = { puts: Put[]; gets: number; resorts: unknown[] };

async function answerResort(options: WireOptions, request: Request, seen: Seen): Promise<Response> {
  const body: unknown = await request.json();
  seen.resorts.push(body);
  return options.resort ? options.resort(body) : json({ requestId: "5b0c1c2e-1b1e-4c52-9d0e-0a6a1b1c00bb", threshold: 50 }, 201);
}

async function answerList(options: WireOptions, request: Request, seen: Seen): Promise<Response> {
  if (request.method === "GET") {
    seen.gets += 1;
    return options.get ? options.get() : json(LIST);
  }
  const body = (await request.json()) as Put["body"];
  seen.puts.push({ body, token: request.headers.get("X-CSRF-Token") });
  return options.put ? options.put(body) : json({ ...LIST, version: body.version + 1 });
}

/** The routes of the Categories page: the list (GET answers `get`; PUT goes to `put`, default: echo at the next version), the plan and the sort-again request. */
export function wire(options: WireOptions = {}): Wired {
  const seen: Seen = { puts: [], gets: 0, resorts: [] };
  const routes: Record<string, (request: Request) => Answer> = {
    "/api/resort-requests/latest": () => (options.latest ? options.latest() : json({ threshold: 50 })),
    "/api/plan": () => (options.plan ? options.plan() : json(NO_OPEN_PLAN)),
    "/api/resort-requests": (request) => answerResort(options, request, seen),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const request = new Request(new URL(input, "http://localhost"), init);
      const route = routes[new URL(request.url).pathname];
      return route ? route(request) : answerList(options, request, seen);
    }),
  );
  return { puts: seen.puts, gets: () => seen.gets, resorts: seen.resorts };
}

/** The page inside a data router (the unsaved-changes guard needs one), with a second route to leave to. */
export function renderPageInRouter(path = "/categories"): { container: HTMLElement; router: ReturnType<typeof createMemoryRouter> } {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/categories", element: <CategoriesPage /> },
      { path: "/elsewhere", element: <p>Elsewhere page</p> },
    ],
    { initialEntries: [path] },
  );
  const { container } = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { container, router };
}

export function renderPage(): HTMLElement {
  return renderPageInRouter().container;
}
