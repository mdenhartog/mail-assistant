import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeEach, vi } from "vitest";

import { App, routes } from "@/App";
import { setCsrfToken } from "@/api/client";
import { expectNoAxeViolations } from "@/test/axe";

const VALUES = {
  timeZone: "Europe/Amsterdam",
  quietStart: "23:00",
  quietEnd: "07:00",
  overviewAt: "18:00",
  remindAt: "09:00",
};
const STORED = { values: VALUES, version: 3, updatedAt: "2026-11-12T13:02:00Z", updatedVia: "telegram" };
const SESSION = {
  maskedAddress: "m***@example.com",
  csrfToken: "csrf-secret-4711",
  idleExpiresAt: "2026-11-12T12:00:00Z",
  absoluteExpiresAt: "2026-11-12T23:00:00Z",
  noticeIntervalMinutes: 5,
};
const SENT = { maskedAddress: SESSION.maskedAddress, expiresAt: "2026-11-12T10:10:00Z", resendAfterSeconds: 60 };
const KEY = "settings-draft";
const HOUR = 60 * 60 * 1000;
const NOW = Date.parse("2026-11-12T10:00:00Z");
const KEPT = "what you typed is kept";
const RESTORED = "Your unsaved changes are restored. Check them and save.";

type Router = ReturnType<typeof createMemoryRouter>;
type Put = (body: { values: typeof VALUES; version: number }) => Response;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

interface Wire {
  puts: { values: typeof VALUES; version: number }[];
  signOuts: number;
}

type Sent = { values: typeof VALUES; version: number };

function sentOf(init: RequestInit | undefined): Sent {
  return JSON.parse(typeof init?.body === "string" ? init.body : "null") as Sent;
}

/** The API: a session while signed in; a 401 on PUT ends it; a right code starts it again. */
function wire(options: { put?: Put; stored?: unknown; signedIn?: boolean } = {}): Wire {
  const seen: Wire = { puts: [], signOuts: 0 };
  let signedIn = options.signedIn ?? true;
  const put = (init: RequestInit | undefined): Response => {
    const body = sentOf(init);
    seen.puts.push(body);
    const answer = options.put ? options.put(body) : json({ ...STORED, values: body.values, version: body.version + 1 });
    signedIn = answer.status === 401 ? false : signedIn;
    return answer;
  };
  const answers: Record<string, (init: RequestInit | undefined) => Response> = {
    "GET /api/session": () => (signedIn ? json(SESSION) : new Response(null, { status: 401 })),
    "POST /auth/request-code": () => json(SENT),
    "POST /auth/verify-code": () => {
      signedIn = true;
      return new Response(null, { status: 204 });
    },
    "POST /auth/logout": () => {
      seen.signOuts += 1;
      signedIn = false;
      return new Response(null, { status: 204 });
    },
    "GET /api/settings": () => json(options.stored ?? STORED),
    "PUT /api/settings": put,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string, init?: RequestInit) => {
      const route = `${(init?.method ?? "GET").toUpperCase()} ${new URL(input, "http://localhost").pathname}`;
      return Promise.resolve(answers[route]?.(init) ?? new Response(null, { status: 404 }));
    }),
  );
  return seen;
}

function setup(path = "/settings", now = NOW): Router {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<App clock={{ now: () => now }} queryClient={client} router={router} />);
  return router;
}

function seed(values: Partial<typeof VALUES>, options: { version?: number; savedAt?: number } = {}): void {
  window.sessionStorage.setItem(
    KEY,
    JSON.stringify({ values: { ...VALUES, ...values }, version: options.version ?? 3, savedAt: options.savedAt ?? NOW }),
  );
}

function stored(): { values: Record<string, unknown>; version: unknown; savedAt: unknown } | null {
  const raw = window.sessionStorage.getItem(KEY);
  return raw === null ? null : (JSON.parse(raw) as { values: Record<string, unknown>; version: unknown; savedAt: unknown });
}

async function loaded(): Promise<void> {
  await screen.findByLabelText("Daily overview");
}

async function typeRemind(user: ReturnType<typeof userEvent.setup>, value: string): Promise<void> {
  const field = screen.getByLabelText("Remind-me-later default");
  await user.clear(field);
  await user.type(field, value);
}

const saveButton = (): HTMLElement => screen.getByRole("button", { name: /^(Save changes|Saving\.\.\.)$/ });

beforeEach(() => {
  setCsrfToken(null);
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  setCsrfToken(null);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("the draft is kept while typing (criterion 3)", () => {
  it("given edited fields, when read from sessionStorage, then it holds the five values and the version, nothing else", async () => {
    wire();
    const user = userEvent.setup();
    setup();
    await loaded();

    await typeRemind(user, "10:30");

    const draft = stored();
    expect(draft).not.toBeNull();
    expect(Object.keys(draft?.values ?? {}).sort()).toEqual(Object.keys(VALUES).sort());
    expect(draft?.values["remindAt"]).toBe("10:30");
    expect(draft?.version).toBe(3);
    expect(Object.keys(draft ?? {}).sort()).toEqual(["savedAt", "values", "version"]);
  });

  it("given the session address and the CSRF token, when the draft is stored, then neither is in any storage", async () => {
    wire();
    const user = userEvent.setup();
    setup();
    await loaded();

    await typeRemind(user, "10:30");

    const everything = [window.sessionStorage, window.localStorage]
      .flatMap((area) => Object.keys(area).map((key) => `${key}=${area.getItem(key) ?? ""}`))
      .join(";");
    expect(everything).not.toContain(SESSION.csrfToken);
    expect(everything).not.toContain("example.com");
    expect(window.localStorage.length).toBe(0);
  });

  it("given the edits are typed back to the stored values, when read, then no draft is kept", async () => {
    wire();
    const user = userEvent.setup();
    setup();
    await loaded();

    await typeRemind(user, "10:30");
    await typeRemind(user, "09:00");

    expect(stored()).toBeNull();
  });
});

describe("a 401 on save (criteria 1 and 2)", () => {
  it("given a 401 on save, when the user signs in again, then the typed values are back with the banner and nothing was sent for them", async () => {
    const seen = wire({ put: () => json({ detail: "No session" }, 401) });
    const user = userEvent.setup();
    const router = setup();
    await loaded();
    await typeRemind(user, "10:30");
    await user.click(saveButton());

    expect(await screen.findByText(new RegExp(KEPT))).toBeInTheDocument();
    await user.type(screen.getByLabelText("Username"), "marco");
    await user.click(screen.getByRole("button", { name: "Send me a code" }));
    await user.type(await screen.findByLabelText("Code"), "123456");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await loaded();
    expect(router.state.location.pathname).toBe("/settings");
    expect(screen.getByLabelText("Remind-me-later default")).toHaveValue("10:30");
    expect(screen.getByText("Welcome back.").closest("[role='status']")).toHaveTextContent(RESTORED);
    expect(seen.puts).toHaveLength(1);
  });

  it("given a restored draft, when the page loads, then Save is enabled and nothing is sent until it is pressed", async () => {
    const seen = wire();
    seed({ remindAt: "10:30" });
    const user = userEvent.setup();
    setup();
    await loaded();

    expect(screen.getByLabelText("Remind-me-later default")).toHaveValue("10:30");
    expect(saveButton()).toBeEnabled();
    expect(seen.puts).toHaveLength(0);

    await user.click(saveButton());

    await waitFor(() => {
      expect(seen.puts).toEqual([{ values: { ...VALUES, remindAt: "10:30" }, version: 3 }]);
    });
  });

  it("given a draft equal to the stored values, when the page loads, then no banner shows and the draft is dropped", async () => {
    wire();
    seed({});
    setup();
    await loaded();

    expect(screen.queryByText(RESTORED)).not.toBeInTheDocument();
    await waitFor(() => {
      expect(stored()).toBeNull();
    });
  });
});

describe("the draft is removed (criterion 4)", () => {
  it("given a draft, when Marco signs out, then it is gone", async () => {
    const seen = wire();
    seed({ remindAt: "10:30" });
    const user = userEvent.setup();
    setup();
    await loaded();

    await user.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => {
      expect(seen.signOuts).toBe(1);
    });
    expect(stored()).toBeNull();
  });

  it("given a draft, when a save succeeds, then it is gone and the banner with it", async () => {
    wire();
    seed({ remindAt: "10:30" });
    const user = userEvent.setup();
    setup();
    await loaded();

    await user.click(saveButton());

    expect(await screen.findByText(/^Saved at/)).toBeInTheDocument();
    expect(stored()).toBeNull();
    expect(screen.queryByText(RESTORED)).not.toBeInTheDocument();
  });

  it("given a 409, when Keep Telegram's is used for every edited field, then the draft is gone", async () => {
    const current = { ...STORED, version: 4, values: { ...VALUES, remindAt: "10:00" } };
    wire({ put: () => json({ current }, 409) });
    const user = userEvent.setup();
    setup();
    await loaded();
    await typeRemind(user, "10:30");
    expect(stored()).not.toBeNull();
    await user.click(saveButton());

    await user.click(await screen.findByRole("button", { name: "Keep Telegram's for Remind-me-later default" }));

    expect(screen.getByLabelText("Remind-me-later default")).toHaveValue("10:00");
    expect(stored()).toBeNull();
  });
});

describe("the stored version moved on (criterion 5)", () => {
  it("given a draft of an older version, when restored, then the conflict flow shows the draft as the typed values", async () => {
    const current = { ...STORED, version: 5, values: { ...VALUES, remindAt: "10:00" } };
    const seen = wire({ stored: current });
    seed({ remindAt: "10:30" }, { version: 3 });
    setup();
    await loaded();

    expect(await screen.findByText(/Settings changed in Telegram/)).toBeInTheDocument();
    expect(screen.getByText("You typed 10:30, Telegram now has 10:00")).toBeInTheDocument();
    expect(screen.getByLabelText("Remind-me-later default")).toHaveValue("10:00");
    expect(screen.queryByText(RESTORED)).not.toBeInTheDocument();
    expect(seen.puts).toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: "Use mine for Remind-me-later default" }));

    expect(screen.getByLabelText("Remind-me-later default")).toHaveValue("10:30");
  });
});

describe("the age of the draft (criterion 6)", () => {
  it("given a draft of 11 h 59 min, when the page loads, then it is restored", async () => {
    wire();
    seed({ remindAt: "10:30" }, { savedAt: NOW - 12 * HOUR + 60_000 });
    setup();
    await loaded();

    expect(screen.getByLabelText("Remind-me-later default")).toHaveValue("10:30");
    expect(screen.getByText(RESTORED)).toBeInTheDocument();
  });

  it("given a draft of 12 h 00 min, when the page loads, then it is discarded and removed", async () => {
    wire();
    seed({ remindAt: "10:30" }, { savedAt: NOW - 12 * HOUR });
    setup();
    await loaded();

    expect(screen.getByLabelText("Remind-me-later default")).toHaveValue("09:00");
    expect(screen.queryByText(RESTORED)).not.toBeInTheDocument();
    expect(stored()).toBeNull();
  });

  it.each([["not json"], [JSON.stringify({ values: { remindAt: 5 }, version: 3, savedAt: NOW })], [JSON.stringify(null)]])(
    "given a damaged draft %s, when the page loads, then it is ignored and removed",
    async (raw) => {
      wire();
      window.sessionStorage.setItem(KEY, raw);
      setup();
      await loaded();

      expect(screen.getByLabelText("Remind-me-later default")).toHaveValue("09:00");
      expect(window.sessionStorage.getItem(KEY)).toBeNull();
    },
  );
});

describe("the login page (criterion 7)", () => {
  it("given a draft, when the expired notice shows, then it says what you typed is kept", async () => {
    wire({ signedIn: false });
    seed({ remindAt: "10:30" });
    setup("/login?notice=expired");

    expect(await screen.findByText("Your session ended.")).toBeInTheDocument();
    expect(screen.getByText(/Sign in again; what you typed is kept\./)).toBeInTheDocument();
  });

  it("given no draft, when the expired notice shows, then it does not", async () => {
    wire({ signedIn: false });
    setup("/login?notice=expired");

    expect(await screen.findByText("Your session ended.")).toBeInTheDocument();
    expect(screen.getByText("Sign in again.")).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(KEPT))).not.toBeInTheDocument();
  });
});

describe("storage that does not work", () => {
  it("given writes that throw, when Marco types and saves, then the page works without a draft", async () => {
    const seen = wire();
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    const user = userEvent.setup();
    setup();
    await loaded();

    await typeRemind(user, "10:30");
    await user.click(saveButton());

    expect(await screen.findByText(/^Saved at/)).toBeInTheDocument();
    expect(seen.puts).toHaveLength(1);
  });

  it("given reads that throw, when the page loads, then it shows the stored values", async () => {
    wire();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    setup();
    await loaded();

    expect(screen.getByLabelText("Remind-me-later default")).toHaveValue("09:00");
  });

  it("given no sessionStorage at all, when Marco types, signs out and sees the login page, then nothing breaks", async () => {
    const seen = wire();
    vi.spyOn(window, "sessionStorage", "get").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    const user = userEvent.setup();
    setup();
    await loaded();

    await typeRemind(user, "10:30");
    expect(saveButton()).toBeEnabled();
    await user.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => {
      expect(seen.signOuts).toBe(1);
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
  });
});

describe("the restore banner (criterion 8)", () => {
  it("given a restored draft, when rendered, then the banner is a status region and axe finds nothing", async () => {
    wire();
    seed({ remindAt: "10:30" });
    setup();
    await loaded();

    const banner = screen.getByText("Welcome back.").closest("[role]");
    expect(banner).toHaveAttribute("role", "status");
    expect(banner).toHaveTextContent(`Welcome back. ${RESTORED}`);
    await expectNoAxeViolations(document.body);
  });
});
