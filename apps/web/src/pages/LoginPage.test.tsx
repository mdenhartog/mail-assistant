import { QueryClient } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeEach, vi } from "vitest";

import { App, routes } from "@/App";
import { setCsrfToken } from "@/api/client";
import { expectNoAxeViolations } from "@/test/axe";

const MASKED = "m***@example.com";
const SESSION = {
  maskedAddress: MASKED,
  csrfToken: "csrf-secret-4711",
  idleExpiresAt: "2026-11-12T12:00:00Z",
  absoluteExpiresAt: "2026-11-12T23:00:00Z",
  noticeIntervalMinutes: 5,
};
const SENT = { maskedAddress: MASKED, expiresAt: "2026-11-12T10:10:00Z", resendAfterSeconds: 60 };

interface Posted {
  path: string;
  body: unknown;
}
type Verify = () => Response;
type Router = ReturnType<typeof createMemoryRouter>;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Stubs the API: no session until a verify answered 204; records every POST body. */
function stubApi(verify: Verify = () => new Response(null, { status: 204 })): Posted[] {
  const posted: Posted[] = [];
  let signedIn = false;
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string, init?: RequestInit) => {
      const path = new URL(input, "http://localhost").pathname;
      if (init?.method === "POST") {
        posted.push({ path, body: JSON.parse(typeof init.body === "string" ? init.body : "null") as unknown });
      }
      if (path === "/api/session") {
        return Promise.resolve(signedIn ? json(SESSION) : new Response(null, { status: 401 }));
      }
      if (path === "/auth/request-code") {
        return Promise.resolve(json(SENT));
      }
      if (path === "/auth/verify-code") {
        const answer = verify();
        signedIn = answer.status === 204;
        return Promise.resolve(answer);
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    }),
  );
  return posted;
}

/** A request that stays pending until `release` is called. */
function stubPending(): { release: (response: Response) => void } {
  const handle: { release: (response: Response) => void } = { release: () => undefined };
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string) => {
      const path = new URL(input, "http://localhost").pathname;
      if (path === "/api/session") {
        return Promise.resolve(new Response(null, { status: 401 }));
      }
      return new Promise<Response>((resolve) => {
        handle.release = resolve;
      });
    }),
  );
  return handle;
}

function setup(path = "/login"): { router: Router; unmount: () => void } {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { unmount } = render(<App router={router} queryClient={client} />);
  return { router, unmount };
}

async function askForCode(user: ReturnType<typeof userEvent.setup>, username = "marco"): Promise<void> {
  await user.type(await screen.findByLabelText("Username"), username);
  await user.click(screen.getByRole("button", { name: "Send me a code" }));
  await screen.findByRole("heading", { level: 1, name: "Enter your code" });
}

async function toCodeStep(): Promise<ReturnType<typeof userEvent.setup>> {
  const user = userEvent.setup();
  setup();
  await askForCode(user);
  return user;
}

async function submitCode(user: ReturnType<typeof userEvent.setup>, code: string): Promise<void> {
  await user.type(screen.getByLabelText("Code"), code);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  setCsrfToken(null);
  vi.unstubAllGlobals();
});

describe("step 1: username", () => {
  it("given /login, when rendered, then h1 is first in main, the username is the first control and the fine print says no mail access", async () => {
    stubApi();
    setup();

    const heading = await screen.findByRole("heading", { level: 1, name: "Sign in" });
    const main = screen.getByRole("main");
    expect(main.querySelector("h1, h2, h3, p, input, button")).toBe(heading);
    const username = screen.getByLabelText("Username");
    expect(main.querySelector("input, button, select, textarea")).toBe(username);
    expect(username).toHaveAttribute("autocomplete", "username");
    expect(screen.getByRole("button", { name: "Send me a code" })).toBeInTheDocument();
    expect(screen.getByText(/one-time code to the e-mail address on file/)).toBeInTheDocument();
    expect(screen.getByText(/never asks for access to your mail or calendar/)).toBeInTheDocument();
    expect(screen.queryByText(/provider|Google|Microsoft/i)).not.toBeInTheDocument();
    await expectNoAxeViolations(document.body);
  });

  it("given the request runs, when pressed, then the button is busy, inputs are read-only and a polite status says so", async () => {
    const pending = stubPending();
    const user = userEvent.setup();
    setup();

    await user.type(await screen.findByLabelText("Username"), "marco");
    await user.click(screen.getByRole("button", { name: "Send me a code" }));

    const button = await screen.findByRole("button", { name: "Sending..." });
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByLabelText("Username")).toHaveAttribute("readonly");
    expect(screen.getByText("Sending your code.")).toHaveAttribute("role", "status");
    await expectNoAxeViolations(document.body);
    await act(async () => {
      pending.release(json(SENT));
      await Promise.resolve();
    });
    await screen.findByRole("heading", { level: 1, name: "Enter your code" });
  });

  it("given an empty username, when sent, then an inline error shows and no request is made", async () => {
    const posted = stubApi();
    const user = userEvent.setup();
    setup();

    await user.click(await screen.findByRole("button", { name: "Send me a code" }));

    const field = screen.getByLabelText("Username");
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Enter your username.");
    expect(field).toHaveFocus();
    expect(posted).toEqual([]);
  });

  it("given the server refuses the request, when shown, then a danger banner shows and the form stays usable", async () => {
    const pending = stubPending();
    const user = userEvent.setup();
    setup();

    await user.type(await screen.findByLabelText("Username"), "marco");
    await user.click(screen.getByRole("button", { name: "Send me a code" }));
    await act(async () => {
      pending.release(new Response(null, { status: 422 }));
      await Promise.resolve();
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not ask for a code.");
    expect(screen.getByRole("button", { name: "Send me a code" })).not.toHaveAttribute("aria-disabled");
    expect(screen.getByLabelText("Username")).not.toHaveAttribute("readonly");
  });
});

describe("step 2: code", () => {
  it("given the same answer for a known and an unknown username, when step 2 appears, then focus is in the code field and the pages are identical", async () => {
    stubApi();
    const first = setup();
    await askForCode(userEvent.setup(), "marco");
    const code = screen.getByLabelText("Code");
    expect(code).toHaveFocus();
    expect(code).toHaveAttribute("inputmode", "numeric");
    expect(code).toHaveAttribute("autocomplete", "one-time-code");
    expect(code).toHaveAttribute("maxlength", "6");
    expect(code).toHaveAccessibleDescription(/We sent a code to m\*\*\*@example\.com\. It is valid for 10 minutes\./);
    expect(screen.getByText(/No code after a few minutes\?/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use another username" })).toBeInTheDocument();
    expect(screen.getByText(`Code sent to ${MASKED}. It is valid for 10 minutes.`)).toHaveAttribute("role", "status");
    await expectNoAxeViolations(document.body);
    const known = document.body.innerHTML;
    first.unmount();

    stubApi();
    setup();
    await askForCode(userEvent.setup(), "nobody-by-that-name");

    expect(document.body.innerHTML).toBe(known);
  });

  it("given a pasted code with a space, when submitted, then the digits are posted and letters are not accepted", async () => {
    const posted = stubApi();
    const user = await toCodeStep();
    const code = screen.getByLabelText("Code");

    await user.type(code, "ab1x");
    expect(code).toHaveValue("1");
    await user.clear(code);
    await user.click(code);
    await user.paste("123 456");
    expect(code).toHaveValue("123456");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(posted.some((p) => p.path === "/auth/verify-code")).toBe(true);
    });
    expect(posted.find((p) => p.path === "/auth/verify-code")?.body).toEqual({ code: "123456" });
  });

  it.each(["/login", "/login?returnTo=%2Fevil", "/login?returnTo=https%3A%2F%2Fevil.example"])(
    "given a right code on %s, when posted, then the browser goes to /settings",
    async (path) => {
      stubApi(() => new Response(null, { status: 204, headers: { "X-Return-To": "/somewhere-else" } }));
      const user = userEvent.setup();
      const { router } = setup(path);
      await askForCode(user);
      await submitCode(user, "123456");

      await screen.findByRole("heading", { level: 1, name: "Settings" });
      expect(router.state.location.pathname).toBe("/settings");
    },
  );

  it("given a 400 with attemptsLeft 3, when shown, then an alert linked to the selected, invalid field says so", async () => {
    stubApi(() => json({ attemptsLeft: 3 }, 400));
    const user = await toCodeStep();
    await submitCode(user, "111111");

    const alert = await screen.findByRole("alert");
    const code = screen.getByLabelText<HTMLInputElement>("Code");
    expect(alert).toHaveTextContent("That code is not right. You have 3 tries left.");
    expect(alert).toHaveTextContent("!");
    expect(code).toHaveAttribute("aria-invalid", "true");
    expect(code.getAttribute("aria-describedby")).toContain(alert.id);
    expect(code).toHaveFocus();
    expect([code.selectionStart, code.selectionEnd]).toEqual([0, 6]);
    await expectNoAxeViolations(document.body);
  });

  it("given a 400 for the last try, when shown, then the number reads in the singular", async () => {
    stubApi(() => json({ attemptsLeft: 1 }, 400));
    const user = await toCodeStep();
    await submitCode(user, "111111");

    expect(await screen.findByRole("alert")).toHaveTextContent("That code is not right. You have 1 try left.");
  });

  it.each([[{}], [null], [{ attemptsLeft: "3" }]])(
    "given a 400 body %j without a usable number, when shown, then the text has no number",
    async (body) => {
      stubApi(() => json(body, 400));
      const user = await toCodeStep();
      await submitCode(user, "111111");

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(/^!\s*That code is not right\.$/);
    },
  );

  it("given a 400 with no body at all, when shown, then the text has no number", async () => {
    stubApi(() => new Response(null, { status: 400 }));
    const user = await toCodeStep();
    await submitCode(user, "111111");

    expect(await screen.findByRole("alert")).toHaveTextContent(/^!\s*That code is not right\.$/);
  });

  it("given a pending verify, when pressed, then the button reads Signing in and the field is read-only", async () => {
    stubApi();
    const user = await toCodeStep();
    const pending = stubPending();
    await submitCode(user, "123456");

    const button = await screen.findByRole("button", { name: "Signing in..." });
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(screen.getByLabelText("Code")).toHaveAttribute("readonly");
    await act(async () => {
      pending.release(json({}, 400));
      await Promise.resolve();
    });
  });

  it("given step 2, when Use another username is pressed, then step 1 returns with an empty field and the code is gone", async () => {
    stubApi();
    const user = await toCodeStep();
    await user.type(screen.getByLabelText("Code"), "123456");

    await user.click(screen.getByRole("button", { name: "Use another username" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByLabelText("Username")).toHaveValue("");
    expect(screen.queryByLabelText("Code")).not.toBeInTheDocument();
  });

  it("given the whole flow, when inspected, then no storage, cookie or URL holds the username, code or address", async () => {
    stubApi(() => json({ attemptsLeft: 2 }, 400));
    const user = userEvent.setup();
    const { router } = setup();
    await askForCode(user);
    await submitCode(user, "654321");
    await screen.findByRole("alert");

    const everything = JSON.stringify([
      Object.entries(window.localStorage),
      Object.entries(window.sessionStorage),
      document.cookie,
      router.state.location,
    ]);
    for (const secret of ["marco", "654321", "m***", "example.com"]) {
      expect(everything).not.toContain(secret);
    }
  });

  it("given the keyboard only, when tabbing step 2, then the controls come in reading order", async () => {
    stubApi();
    const user = await toCodeStep();

    expect(screen.getByLabelText("Code")).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Sign in" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Use another username" })).toHaveFocus();
  });
});

describe("notices", () => {
  it("given ?notice=expired, when rendered, then the session-ended status shows after the heading", async () => {
    stubApi();
    setup("/login?notice=expired");

    const heading = await screen.findByRole("heading", { level: 1, name: "Sign in" });
    const status = screen.getByText(/Your session ended\./).closest("[role=status]");
    expect(status).toHaveTextContent("Your session ended. Sign in again.");
    expect(heading.compareDocumentPosition(status as Element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await expectNoAxeViolations(document.body);
  });

  it.each(["%3Cscript%3Ealert(1)%3C%2Fscript%3E", "other", ""])(
    "given the unknown notice %j, when rendered, then no notice shows and nothing from the URL is in the DOM",
    async (value) => {
      stubApi();
      setup(`/login?notice=${value}`);

      await screen.findByRole("heading", { level: 1, name: "Sign in" });
      expect(screen.queryByText(/Your session ended/)).not.toBeInTheDocument();
      expect(document.body.innerHTML).not.toContain("script");
      expect(document.body.innerHTML).not.toContain("other");
    },
  );
});
