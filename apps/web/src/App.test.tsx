import { QueryClient } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeEach, vi } from "vitest";

import { App, routes } from "@/App";
import { apiFetch, setCsrfToken } from "@/api/client";
import { expectNoAxeViolations } from "@/test/axe";

const SESSION = {
  maskedAddress: "m***@example.com",
  csrfToken: "csrf-secret-4711",
  idleExpiresAt: "2026-11-12T12:00:00Z",
  absoluteExpiresAt: "2026-11-12T23:00:00Z",
  noticeIntervalMinutes: 5,
};

type Handler = (request: Request) => Response;
type TestRouter = ReturnType<typeof createMemoryRouter>;

function stubFetch(handler: Handler): ReturnType<typeof vi.fn> {
  const mock = vi.fn((input: string, init?: RequestInit) =>
    Promise.resolve(handler(new Request(new URL(input, "http://localhost"), init))),
  );
  vi.stubGlobal("fetch", mock);
  return mock;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const SETTINGS = {
  values: { timeZone: "Europe/Amsterdam", quietStart: "23:00", quietEnd: "07:00", overviewAt: "18:00", remindAt: "09:00" },
  version: 1,
  updatedAt: null,
  updatedVia: null,
};

/** The settings page loads its values; every other path is unknown unless the test says otherwise. */
function settingsOrNotFound(request: Request): Response {
  const isLoad = request.method === "GET" && new URL(request.url).pathname === "/api/settings";
  return isLoad ? json(SETTINGS) : new Response(null, { status: 404 });
}

function withSession(extra: Handler = settingsOrNotFound): Handler {
  return (request) => (new URL(request.url).pathname === "/api/session" ? json(SESSION) : extra(request));
}

function setup(path: string): { router: TestRouter; client: QueryClient } {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<App router={router} queryClient={client} />);
  return { router, client };
}

function dump(storage: Storage): string {
  return JSON.stringify(Object.entries(storage));
}

async function settingsShown(): Promise<void> {
  await screen.findByRole("heading", { level: 1, name: "Settings" });
}

async function settingsLoaded(): Promise<void> {
  await screen.findByLabelText("Time zone");
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
});

afterEach(() => {
  setCsrfToken(null);
  vi.unstubAllGlobals();
});

describe("routing and session", () => {
  it("given GET /api/session answers 401, when /settings is opened, then the app shows /login", async () => {
    stubFetch(() => new Response(null, { status: 401 }));

    const { router } = setup("/settings");

    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
  });

  it("given a valid session, when /login is opened, then the app shows /settings", async () => {
    stubFetch(withSession());

    const { router } = setup("/login");

    await settingsShown();
    expect(router.state.location.pathname).toBe("/settings");
  });

  it("given the root path with a session, when opened, then it goes to /settings", async () => {
    stubFetch(withSession());

    const { router } = setup("/");

    await settingsShown();
    expect(router.state.location.pathname).toBe("/settings");
  });

  it("given an unknown path, when opened, then a not-found page with a way back is shown", async () => {
    stubFetch(withSession());

    setup("/nope");

    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to settings" })).toHaveAttribute("href", "/settings");
  });

  it.each([
    ["/settings", "Settings - Mail Assistant"],
    ["/nope", "Page not found - Mail Assistant"],
  ])("given %s, when shown, then the page title is %s", async (path, title) => {
    stubFetch(withSession());

    setup(path);

    await waitFor(() => {
      expect(document.title).toBe(title);
    });
  });

  it("given the login page, when shown, then the page title is Sign in", async () => {
    stubFetch(() => new Response(null, { status: 401 }));

    setup("/login");

    await waitFor(() => {
      expect(document.title).toBe("Sign in - Mail Assistant");
    });
  });

  it("given the settings shell, when checked, then it shows the masked address and has no axe violations", async () => {
    stubFetch(withSession());

    setup("/settings");
    await settingsShown();

    expect(screen.getByText(/m\*\*\*@example\.com/)).toBeInTheDocument();
    await expectNoAxeViolations(document.body);
  });
});

describe("csrf token", () => {
  it("given a session, when the app runs, then the token is in no storage, cookie or URL", async () => {
    stubFetch(withSession());

    const { router } = setup("/settings");
    await settingsShown();

    expect(dump(window.localStorage)).not.toContain(SESSION.csrfToken);
    expect(dump(window.sessionStorage)).not.toContain(SESSION.csrfToken);
    expect(document.cookie).not.toContain(SESSION.csrfToken);
    expect(window.location.href).not.toContain(SESSION.csrfToken);
    expect(router.state.location.search + router.state.location.pathname).not.toContain(SESSION.csrfToken);
    expect(window.localStorage).toHaveLength(0);
    expect(window.sessionStorage).toHaveLength(0);
  });

  it("given a PUT and a GET, when sent, then only the write carries X-CSRF-Token", async () => {
    const seen: Request[] = [];
    stubFetch(
      withSession((request) => {
        seen.push(request);
        return request.method === "GET" ? json(SETTINGS) : json({});
      }),
    );
    setup("/settings");
    await settingsLoaded();
    seen.length = 0;

    await apiFetch("/api/settings");
    await apiFetch("/api/settings", { method: "PUT", body: "{}" });

    expect(seen.map((r) => [r.method, r.headers.get("X-CSRF-Token")])).toEqual([
      ["GET", null],
      ["PUT", SESSION.csrfToken],
    ]);
  });
});

describe("failures", () => {
  it("given a 401 on a write and on a background refetch, when received, then each goes to the expired login, nothing retried", async () => {
    let expired = false;
    const mock = stubFetch((request) => {
      if (new URL(request.url).pathname === "/api/session") {
        return expired ? new Response(null, { status: 401 }) : json(SESSION);
      }
      expired = true;
      return new Response(null, { status: 401 });
    });
    const { router, client } = setup("/settings");
    await settingsShown();

    await act(async () => {
      await apiFetch("/api/settings", { method: "PUT", body: "{}" }).catch(() => undefined);
    });
    await waitFor(() => {
      expect(router.state.location.pathname + router.state.location.search).toBe("/login?notice=expired");
    });
    await act(async () => {
      await router.navigate("/login");
    });
    await act(async () => {
      await client
        .query({ queryKey: ["settings"], queryFn: () => apiFetch("/api/settings"), staleTime: 0 })
        .catch(() => undefined);
    });

    await waitFor(() => {
      expect(router.state.location.pathname + router.state.location.search).toBe("/login?notice=expired");
    });
    const settingsCalls = mock.mock.calls.filter(([url]) => url === "/api/settings");
    // The page's own load, the write and the refetch: each request once, none repeated.
    expect(settingsCalls).toHaveLength(3);
  });

  it("given a 403, when received, then the refusal page replaces the app and no settings value stays in the DOM", async () => {
    stubFetch(withSession(() => new Response(null, { status: 403 })));
    setup("/settings");
    await screen.findByText(/m\*\*\*@example\.com/);

    await act(async () => {
      await apiFetch("/api/settings", { method: "PUT", body: "{}" }).catch(() => undefined);
    });

    expect(await screen.findByText("This request was not allowed.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to sign in" })).toHaveAttribute("href", "/login");
    expect(screen.queryByText(/m\*\*\*@example\.com/)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Settings" })).not.toBeInTheDocument();
    await expectNoAxeViolations(document.body);
  });
});

describe("session errors", () => {
  it("given the session answer is not valid, when /settings is opened, then an alert asks for a reload", async () => {
    stubFetch(() => json({ nonsense: true }));

    setup("/settings");

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load your session");
  });

  it("given the session answer is not valid, when /login is opened, then the sign-in page is shown", async () => {
    stubFetch(() => new Response(null, { status: 500 }));

    setup("/login");

    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
  });

  it("given the refusal page, when Back to sign in is pressed, then the sign-in page is shown", async () => {
    let refused = true;
    stubFetch((request) => {
      if (new URL(request.url).pathname === "/api/session") {
        return refused ? json(SESSION) : new Response(null, { status: 401 });
      }
      return new Response(null, { status: 403 });
    });
    setup("/settings");
    await settingsShown();
    await act(async () => {
      await apiFetch("/api/settings", { method: "PUT", body: "{}" }).catch(() => undefined);
    });
    refused = false;

    await userEvent.click(await screen.findByRole("link", { name: "Back to sign in" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
  });
});

describe("sign out", () => {
  it("given Sign out fails, when pressed, then an alert is shown and the user stays signed in", async () => {
    stubFetch(
      withSession((request) =>
        new URL(request.url).pathname === "/auth/logout" ? new Response(null, { status: 500 }) : settingsOrNotFound(request),
      ),
    );
    setup("/settings");
    await settingsLoaded();

    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not sign out. Try again.");
    expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
  });

  it("given Sign out, when pressed, then POST /auth/logout carries the token and the app shows /login", async () => {
    const seen: Request[] = [];
    stubFetch((request) => {
      if (new URL(request.url).pathname === "/auth/logout") {
        seen.push(request);
        return new Response(null, { status: 204 });
      }
      return seen.length > 0 ? new Response(null, { status: 401 }) : json(SESSION);
    });
    const { router } = setup("/settings");
    await settingsShown();

    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(seen).toHaveLength(1);
    expect(seen[0]?.method).toBe("POST");
    expect(seen[0]?.headers.get("X-CSRF-Token")).toBe(SESSION.csrfToken);
  });
});
