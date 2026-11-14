import { QueryClient } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeEach, vi } from "vitest";

import { App, routes } from "@/App";
import { setCsrfToken } from "@/api/client";
import type { Clock } from "@/pages/clock";
import { expectNoAxeViolations } from "@/test/axe";

const MASKED = "m***@example.com";
const SENT = { maskedAddress: MASKED, expiresAt: "2026-11-12T10:10:00Z", resendAfterSeconds: 60 };
const SENT_TEXT = "A new code was sent. The earlier code no longer works.";
const EXPIRED_TEXT = "This code has expired. Send yourself a new one.";
const EXHAUSTED_TEXT = "Too many wrong tries. This code no longer works. Send a new code.";
const WRONG_TEXT = "That code is not right. You have 3 tries left.";
const MINUTE = 60;

interface Posted {
  path: string;
  body: unknown;
}
interface Stub {
  posted: Posted[];
  request: { next: () => Response };
  verify: { next: () => Response };
}
type User = ReturnType<typeof userEvent.setup>;

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

function tooMany(retryAfter: string): Response {
  return new Response(null, { status: 429, headers: { "Retry-After": retryAfter } });
}

/** Stubs the API; `request.next` and `verify.next` decide the next answer. */
function stubApi(): Stub {
  const stub: Stub = {
    posted: [],
    request: { next: () => json(SENT) },
    verify: { next: () => json({ attemptsLeft: 3 }, 400) },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string, init?: RequestInit) => {
      const path = new URL(input, "http://localhost").pathname;
      if (init?.method === "POST") {
        stub.posted.push({ path, body: JSON.parse(typeof init.body === "string" ? init.body : "null") as unknown });
      }
      if (path === "/api/session") {
        return Promise.resolve(new Response(null, { status: 401 }));
      }
      if (path === "/auth/request-code") {
        return Promise.resolve(stub.request.next());
      }
      if (path === "/auth/verify-code") {
        return Promise.resolve(stub.verify.next());
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    }),
  );
  return stub;
}

/** A clock the test moves by hand; `tick` moves it and lets the page's one-second timer fire once. */
function testClock(): Clock & { tick: (seconds: number) => void } {
  let ms = Date.UTC(2026, 10, 12, 10, 0, 0);
  return {
    now: () => ms,
    tick: (seconds) => {
      ms += seconds * 1000;
      act(() => {
        vi.advanceTimersByTime(1000);
      });
    },
  };
}

function setup(clock: Clock): void {
  const router = createMemoryRouter(routes, { initialEntries: ["/login"] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<App clock={clock} queryClient={client} router={router} />);
}

async function askForCode(user: User): Promise<void> {
  await user.type(await screen.findByLabelText("Username"), "marco");
  await user.click(screen.getByRole("button", { name: "Send me a code" }));
}

async function toCodeStep(clock: Clock): Promise<User> {
  const user = userEvent.setup();
  setup(clock);
  await askForCode(user);
  await screen.findByRole("heading", { level: 1, name: "Enter your code" });
  return user;
}

async function submitCode(user: User, code = "111111"): Promise<void> {
  await user.type(screen.getByLabelText("Code"), code);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

function resendButton(): HTMLElement {
  return screen.getByRole("button", { name: "Send a new code" });
}

/** The visible countdown text: the element that is not announced. */
function countdown(): HTMLElement {
  const element = document.querySelector<HTMLElement>('[aria-live="off"]');
  if (!element) {
    throw new Error("no countdown text");
  }
  return element;
}

/** The hidden polite status of the resend control. */
function announcer(): HTMLElement {
  const element = screen.getAllByRole("status").find((candidate) => /new code/.test(candidate.textContent) && candidate.className.includes("sr-only"));
  if (!element) {
    throw new Error("no hidden status");
  }
  return element;
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
});

afterEach(() => {
  setCsrfToken(null);
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("the countdown on Send a new code", () => {
  it("given a code sent at t, when the clock is at t+0, t+8 and t+60, then the button is disabled, disabled, enabled and the hidden status speaks only at the start and the end", async () => {
    stubApi();
    const clock = testClock();
    await toCodeStep(clock);

    expect(resendButton()).toBeDisabled();
    expect(countdown()).toHaveTextContent("You can ask for a new code in 60 seconds.");
    expect(announcer()).toHaveTextContent("You can ask for a new code in 60 seconds.");
    await expectNoAxeViolations(document.body);

    const changes: MutationRecord[] = [];
    const observer = new MutationObserver((records) => {
      changes.push(...records);
    });
    observer.observe(announcer(), { subtree: true, childList: true, characterData: true });
    clock.tick(8);
    expect(countdown()).toHaveTextContent("You can ask for a new code in 52 seconds.");
    expect(resendButton()).toBeDisabled();
    for (let second = 9; second < 60; second += 1) {
      clock.tick(1);
    }
    expect(countdown()).toHaveTextContent("You can ask for a new code in 1 second.");
    expect(announcer()).toHaveTextContent("You can ask for a new code in 60 seconds.");
    expect(observer.takeRecords()).toEqual([]);
    expect(changes).toEqual([]);

    clock.tick(1);
    expect(resendButton()).toBeEnabled();
    expect(countdown()).toHaveTextContent("You can ask for a new code now.");
    expect(announcer()).toHaveTextContent("You can ask for a new code now.");
    await expectNoAxeViolations(document.body);
    observer.disconnect();
  });

  it("given the countdown runs, when prefers-reduced-motion is set, then the countdown is text only", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn((query: string) => ({ matches: query.includes("reduce"), media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
    );
    stubApi();
    const clock = testClock();
    await toCodeStep(clock);
    clock.tick(5);

    const region = countdown().parentElement;
    expect(region).not.toBeNull();
    expect(region?.querySelector("progress, meter, svg, canvas, [role=progressbar]")).toBeNull();
    expect(countdown().children).toHaveLength(0);
    expect(countdown().className).not.toMatch(/animate|transition/);
    expect(countdown()).toHaveTextContent("You can ask for a new code in 55 seconds.");
  });
});

describe("sending a new code", () => {
  it("given the countdown is over, when Send a new code is pressed, then the notice shows, the field is cleared and focused, and the countdown restarts", async () => {
    const stub = stubApi();
    const clock = testClock();
    const user = await toCodeStep(clock);
    await user.type(screen.getByLabelText("Code"), "12345");
    for (let second = 0; second < 60; second += 1) {
      clock.tick(1);
    }

    await user.click(resendButton());

    expect(await screen.findByText(SENT_TEXT)).toBeInTheDocument();
    expect(screen.getByLabelText("Code")).toHaveValue("");
    expect(screen.getByLabelText("Code")).toHaveFocus();
    expect(resendButton()).toBeDisabled();
    expect(countdown()).toHaveTextContent("You can ask for a new code in 60 seconds.");
    expect(stub.posted.filter((p) => p.path === "/auth/request-code")).toEqual([
      { path: "/auth/request-code", body: { username: "marco" } },
      { path: "/auth/request-code", body: { username: "marco" } },
    ]);
    await expectNoAxeViolations(document.body);
  });

  it("given a wrong code after a new one was sent, when shown, then the notice is gone", async () => {
    const stub = stubApi();
    const clock = testClock();
    const user = await toCodeStep(clock);
    for (let second = 0; second < 60; second += 1) {
      clock.tick(1);
    }
    await user.click(resendButton());
    await screen.findByText(SENT_TEXT);

    stub.verify.next = () => json({ attemptsLeft: 3 }, 400);
    await submitCode(user);

    expect(await screen.findByText(WRONG_TEXT)).toBeInTheDocument();
    expect(screen.queryByText(SENT_TEXT)).not.toBeInTheDocument();
  });
});

describe("asking too soon (429)", () => {
  it("given a 429 with Retry-After 41 on a new code, when shown, then an info banner and the same countdown rule", async () => {
    const stub = stubApi();
    const clock = testClock();
    const user = await toCodeStep(clock);
    for (let second = 0; second < 60; second += 1) {
      clock.tick(1);
    }
    stub.request.next = () => tooMany("41");

    await user.click(resendButton());

    const banner = await screen.findByText(/Please wait before asking for another code\./);
    expect(banner.closest("[role=status]")).toHaveTextContent(
      "Please wait before asking for another code. You can try again in 41 seconds.",
    );
    expect(resendButton()).toBeDisabled();
    expect(countdown()).toHaveTextContent("You can ask for a new code in 41 seconds.");
    expect(screen.queryByText(SENT_TEXT)).not.toBeInTheDocument();
    clock.tick(41);
    expect(resendButton()).toBeEnabled();
    await expectNoAxeViolations(document.body);
  });

  it("given a 429 with Retry-After 41 on step 1, when shown, then the same info banner replaces the generic one", async () => {
    const stub = stubApi();
    stub.request.next = () => tooMany("41");
    const user = userEvent.setup();
    setup(testClock());

    await askForCode(user);

    const banner = await screen.findByText(/Please wait before asking for another code\./);
    expect(banner.closest("[role=status]")).toHaveTextContent("You can try again in 41 seconds.");
    expect(screen.queryByText("Could not ask for a code.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send me a code" })).toBeEnabled();
    await expectNoAxeViolations(document.body);
  });

  it("given a 429 without a usable Retry-After, when shown, then it counts as the normal 60 second cooldown", async () => {
    const stub = stubApi();
    stub.request.next = () => tooMany("Wed, 21 Oct 2026 07:28:00 GMT");
    const user = userEvent.setup();
    setup(testClock());

    await askForCode(user);

    expect(await screen.findByText(/You can try again in 60 seconds\./)).toBeInTheDocument();
  });
});

describe("a new code that could not be sent", () => {
  it("given the request fails with a 500, when shown, then a danger banner says so and the button stays usable", async () => {
    const stub = stubApi();
    const clock = testClock();
    const user = await toCodeStep(clock);
    for (let second = 0; second < 60; second += 1) {
      clock.tick(1);
    }
    stub.request.next = () => new Response(null, { status: 500 });

    await user.click(resendButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not send a new code. Try again.");
    expect(resendButton()).toBeEnabled();
    await expectNoAxeViolations(document.body);
  });
});

describe("too many codes this hour (429)", () => {
  it.each([
    ["1500", "25"],
    ["1501", "26"],
  ])("given a 429 with Retry-After %s, when shown, then an alert says about %s minutes and the button waits", async (retryAfter, minutes) => {
    const stub = stubApi();
    const clock = testClock();
    const user = await toCodeStep(clock);
    for (let second = 0; second < 60; second += 1) {
      clock.tick(1);
    }
    stub.request.next = () => tooMany(retryAfter);

    await user.click(resendButton());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(`You have asked for too many codes this hour. Try again in about ${minutes} minutes.`);
    expect(resendButton()).toBeDisabled();
    clock.tick(Number(retryAfter) - 1);
    expect(resendButton()).toBeDisabled();
    clock.tick(1);
    expect(resendButton()).toBeEnabled();
    expect(countdown()).toHaveTextContent("You can ask for a new code now.");
  });

  it("given a 429 with a long Retry-After on step 1, when shown, then the alert replaces the generic banner and no code step opens", async () => {
    const stub = stubApi();
    stub.request.next = () => tooMany("1500");
    const user = userEvent.setup();
    setup(testClock());

    await askForCode(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("You have asked for too many codes this hour. Try again in about 25 minutes.");
    expect(screen.queryByText("Could not ask for a code.")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    await expectNoAxeViolations(document.body);
  });
});

describe("an expired code", () => {
  it("given a 400 after more than 10 minutes by the clock, when shown, then the expiry alert shows, focus is on Send a new code and the field is cleared", async () => {
    const stub = stubApi();
    const clock = testClock();
    const user = await toCodeStep(clock);
    await user.type(screen.getByLabelText("Code"), "123456");
    clock.tick(MINUTE * 10 + 1);
    stub.verify.next = () => json({ attemptsLeft: 3 }, 400);

    await user.click(screen.getByRole("button", { name: "Sign in" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(EXPIRED_TEXT);
    expect(screen.queryByText(WRONG_TEXT)).not.toBeInTheDocument();
    expect(resendButton()).toHaveFocus();
    expect(screen.getByLabelText("Code")).toHaveValue("");
    await expectNoAxeViolations(document.body);
  });

  it("given a 400 at exactly 10 minutes, when shown, then it is still the ordinary wrong-code text", async () => {
    stubApi();
    const clock = testClock();
    const user = await toCodeStep(clock);
    clock.tick(MINUTE * 10);

    await submitCode(user);

    expect(await screen.findByText(WRONG_TEXT)).toBeInTheDocument();
    expect(screen.queryByText(EXPIRED_TEXT)).not.toBeInTheDocument();
  });
});

describe("too many wrong tries", () => {
  it.each([
    ["attemptsLeft 0", () => json({ attemptsLeft: 0 }, 400)],
    ["a 429 on verify", () => tooMany("600")],
  ])("given %s, when shown, then the alert shows and the code field is disabled until a new code is sent", async (_name, answer) => {
    const stub = stubApi();
    const clock = testClock();
    const user = await toCodeStep(clock);
    stub.verify.next = answer;

    await submitCode(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(EXHAUSTED_TEXT);
    expect(screen.queryByText(/not right/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Code")).toBeDisabled();
    expect(screen.getByLabelText("Code")).toHaveValue("");
    await expectNoAxeViolations(document.body);

    for (let second = 0; second < 60; second += 1) {
      clock.tick(1);
    }
    await user.click(resendButton());

    await waitFor(() => {
      expect(screen.getByLabelText("Code")).toBeEnabled();
    });
    expect(screen.queryByText(EXHAUSTED_TEXT)).not.toBeInTheDocument();
    expect(await screen.findByText(SENT_TEXT)).toBeInTheDocument();
  });
});

describe("a locked web", () => {
  it("given the verify answer of a locked web, when shown, then only the generic refusal text shows and no lock is mentioned", async () => {
    const stub = stubApi();
    const user = await toCodeStep(testClock());
    stub.verify.next = () => json({ attemptsLeft: 3, locked: true, detail: "The web is locked" }, 400);

    await submitCode(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(`!${WRONG_TEXT}`);
    expect(document.body).not.toHaveTextContent(/lock/i);
  });
});
