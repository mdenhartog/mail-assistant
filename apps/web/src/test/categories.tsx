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
  ready: true,
  generalInstructions: "Keep receipts for the tax year.",
  categories: [INVOICES, NEWS],
  other: { mailCount: 7 },
  olderCategories: [{ labelName: "Assistant/Travel", mailCount: null }],
};

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

export interface Put {
  body: {
    version: number;
    generalInstructions: string;
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

/** GET answers `get`; PUT goes to `put` (default: echo the list back at the next version). */
export function wire(options: { get?: () => Answer; put?: (body: Put["body"]) => Answer } = {}): {
  puts: Put[];
  gets: () => number;
} {
  const seen: { puts: Put[]; gets: number } = { puts: [], gets: 0 };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const request = new Request(new URL(input, "http://localhost"), init);
      if (request.method === "GET") {
        seen.gets += 1;
        return options.get ? options.get() : json(LIST);
      }
      const body = (await request.json()) as Put["body"];
      seen.puts.push({ body, token: request.headers.get("X-CSRF-Token") });
      return options.put ? options.put(body) : json({ ...LIST, version: body.version + 1 });
    }),
  );
  return { puts: seen.puts, gets: () => seen.gets };
}

/** The page inside a data router (the unsaved-changes guard needs one), with a second route to leave to. */
export function renderPageInRouter(): { container: HTMLElement; router: ReturnType<typeof createMemoryRouter> } {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/categories", element: <CategoriesPage /> },
      { path: "/elsewhere", element: <p>Elsewhere page</p> },
    ],
    { initialEntries: ["/categories"] },
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
