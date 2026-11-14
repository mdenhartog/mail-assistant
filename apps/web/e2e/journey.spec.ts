import { expect, test } from "@playwright/test";
import type { Browser, Page } from "@playwright/test";

import { axeProblems, settle } from "./support/checks";
import { ageSessions, lockWeb, resetState, seedSettings, sessionCount, storedRow } from "./support/db";
import { clearMailbox, newestCode } from "./support/mailbox";
import { USERNAME } from "./support/session";

// The `journey` project (U-web-settings-43, the R1 release gate): the whole of INT-002 through a real browser over the
// prod-like stack, HTTPS edge and TLS database included. One worker, in file order, after every other project: the
// stack has one allowed user, one mailbox and one settings row. Owner SQL (support/db.ts) puts the row and the sign-in
// tables back before each test. Every test that needs a session signs in through the page, with the code read from the
// mail catcher, because the reset removes the sessions.
test.describe.configure({ timeout: 120_000 });

const SIX_DIGITS = /^\d{6}$/;
const SESSION_COOKIE = "__Host-session";
const AMSTERDAM_ROW = "1|1080|Europe/Amsterdam"; // version, overview 18:00 as minutes, zone
const CSP =
  "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; " +
  "frame-ancestors 'none'; base-uri 'self'; form-action 'self'";
const COOLDOWN_MS = 1_300; // the prod-like api asks for one second between codes
const PUBLIC_ORIGIN = "https://mail-assistant.localhost:8443";

let lastAsk = 0;

test.beforeEach(() => {
  resetState();
});

/** The api refuses a second code within a second of the last one (429); poll until the cooldown has passed. */
async function respectCooldown(): Promise<void> {
  await expect
    .poll(() => Date.now() - lastAsk, { intervals: [100], timeout: COOLDOWN_MS + 1_000 })
    .toBeGreaterThanOrEqual(COOLDOWN_MS);
}

/** Username step, then the code the api mailed to the catcher; returns the code with the code step on screen. */
async function askForCode(page: Page): Promise<string> {
  await respectCooldown();
  await clearMailbox();
  await page.goto("/login");
  await page.getByLabel("Username").fill(USERNAME);
  await page.getByRole("button", { name: "Send me a code" }).click();
  lastAsk = Date.now();
  await expect
    .poll(async () => newestCode().catch(() => ""), { message: "the sign-in mail arrives", timeout: 30_000 })
    .toMatch(SIX_DIGITS);
  await expect(page.getByLabel("Code", { exact: true })).toBeVisible();
  return newestCode();
}

async function signIn(page: Page): Promise<void> {
  const code = await askForCode(page);
  await page.getByLabel("Code", { exact: true }).fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
}

async function newSignedInPage(browser: Browser, baseURL: string | undefined): Promise<Page> {
  const context = await browser.newContext(baseURL ? { baseURL } : {});
  const page = await context.newPage();
  await signIn(page);
  return page;
}

function overviewOf(page: Page): ReturnType<Page["getByLabel"]> {
  return page.getByLabel("Daily overview", { exact: true });
}

// 1 (AC-2)
test("a visitor without a session gets the login page for /settings and 401 from the settings api", async ({
  page,
  request,
}) => {
  await page.goto("/settings");

  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
  expect((await request.get("/api/settings")).status()).toBe(401);
});

// 2 (AC-1, AC-3)
test("a wrong code gets the generic error with the tries left and no session; the right code shows the settings", async ({
  page,
  context,
}) => {
  seedSettings();
  const code = await askForCode(page);
  const wrong = code === "000000" ? "111111" : "000000";

  await page.getByLabel("Code", { exact: true }).fill(wrong);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByText(/That code is not right\. You have \d tr(y|ies) left\./)).toBeVisible();
  expect((await context.cookies()).map((cookie) => cookie.name)).not.toContain(SESSION_COOKIE);
  await expect(page).toHaveURL(/\/login/);

  await page.getByLabel("Code", { exact: true }).fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/settings$/);
  await expect(overviewOf(page)).toHaveValue("18:00");
  await expect(page.getByLabel("From", { exact: true })).toHaveValue("23:00");
  await expect(page.getByText(/^Last changed from Telegram at \d{2}:\d{2}$/)).toBeVisible();
  expect((await context.cookies()).map((cookie) => cookie.name)).toContain(SESSION_COOKIE);
});

// 3 (AC-3)
test("two verify requests with the same code in two tabs: exactly one signs in", async ({ browser, baseURL }) => {
  const context = await browser.newContext(baseURL ? { baseURL } : {});
  const first = await context.newPage();
  const code = await askForCode(first);
  const second = await context.newPage();
  await second.goto("/login");
  await first.getByLabel("Code", { exact: true }).fill(code);
  const answer = first.waitForResponse((response) => response.url().endsWith("/auth/verify-code"));

  const [fromFirst, fromSecond] = await Promise.all([
    (async () => {
      await first.getByRole("button", { name: "Sign in" }).click();
      return (await answer).status();
    })(),
    second.evaluate(async (payload) => {
      const response = await fetch("/auth/verify-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
      });
      return response.status;
    }, JSON.stringify({ code })),
  ]);

  expect([fromFirst, fromSecond].sort()).toEqual([204, 400]);
  expect(sessionCount()).toBe(1);
  await first.goto("/settings");
  await expect(first.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
  await context.close();
});

// 4 (AC-11, AC-28)
test("a save from a second context on version 1 gets the conflict banner with both choices", async ({
  browser,
  baseURL,
}) => {
  seedSettings();
  const pageA = await newSignedInPage(browser, baseURL);
  const pageB = await newSignedInPage(browser, baseURL);
  await expect(overviewOf(pageA)).toHaveValue("18:00");

  await overviewOf(pageB).fill("17:30");
  await pageB.getByRole("button", { name: "Save changes" }).click();
  await expect(pageB.getByText(/^Saved at/)).toBeVisible();

  await overviewOf(pageA).fill("17:00");
  await pageA.getByRole("button", { name: "Save changes" }).click();

  await expect(pageA.getByRole("alert").filter({ hasText: /Settings changed/ })).toBeVisible();
  await expect(pageA.getByRole("button", { name: /^Use mine/ })).toBeVisible();
  await expect(pageA.getByRole("button", { name: /^Keep the stored value/ })).toBeVisible();
  expect(storedRow()).toBe("2|1050|Europe/Amsterdam"); // B's 17:30; A's 17:00 is not stored
  await pageA.context().close();
  await pageB.context().close();
});

// 5 (AC-12, both halves)
test("an expired session stores nothing on Save, keeps the typed value and restores it after sign-in", async ({ page }) => {
  seedSettings();
  await signIn(page);
  ageSessions();

  await overviewOf(page).fill("17:00");
  await page.getByRole("button", { name: "Save changes" }).click();

  await expect(page).toHaveURL(/\/login\?notice=expired$/);
  await expect(page.getByText("Your session ended.")).toBeVisible();
  await expect(page.getByText(/what you typed is kept/)).toBeVisible();
  expect(storedRow()).toBe(AMSTERDAM_ROW);

  await signIn(page);
  await expect(overviewOf(page)).toHaveValue("17:00");
  await expect(page.getByText("Welcome back.")).toBeVisible();
  expect(storedRow()).toBe(AMSTERDAM_ROW); // restored, never saved by itself
});

test("an expired session found by a background refetch sends the browser to sign in again", async ({ page }) => {
  seedSettings();
  await signIn(page);
  ageSessions();

  // The session is stale after a minute; the browser clock is moved on, and a return to the tab refetches it.
  await page.clock.install();
  await page.clock.fastForward(61_000);
  await page.evaluate(() => {
    const show = (state: "hidden" | "visible"): void => {
      Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
      window.dispatchEvent(new Event("visibilitychange")); // TanStack Query's focus manager listens on the window
    };
    show("hidden");
    show("visible");
  });

  await expect(page).toHaveURL(/\/login\?notice=expired$/);
  expect(storedRow()).toBe(AMSTERDAM_ROW);
  await page.clock.resume();

  await signIn(page);
  await expect(overviewOf(page)).toHaveValue("18:00");
});

// 6 (AC-14, W-5)
test("an injected inline script and an external script do not run, the browser reports both, the header matches", async ({
  page,
}) => {
  const response = await page.goto("/login");
  expect(response?.headers()["content-security-policy"]).toBe(CSP);

  await page.evaluate(() => {
    const violations: string[] = [];
    Object.assign(window, { cspViolations: violations });
    document.addEventListener("securitypolicyviolation", (event) => {
      violations.push(event.violatedDirective);
    });
    const inline = document.createElement("script");
    inline.textContent = "window.inlineRan = true";
    document.head.append(inline);
    const external = document.createElement("script");
    external.src = "https://cdn.example.test/injected.js";
    document.head.append(external);
  });
  // The browser reports a violation as an event; poll for both instead of waiting a fixed time.
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { cspViolations: string[] }).cspViolations.length))
    .toBe(2);
  const outcome = await page.evaluate(() => ({
    violations: (window as unknown as { cspViolations: string[] }).cspViolations,
    inlineRan: "inlineRan" in window,
  }));

  expect(outcome.inlineRan).toBe(false);
  expect(outcome.violations).toHaveLength(2);
  for (const directive of outcome.violations) {
    expect(directive).toMatch(/^script-src/);
  }
});

// 7 (AC-18, AC-19)
test("the documentation, health and metrics paths are 404 through the edge; plain HTTP redirects; HSTS is set", async ({
  request,
  baseURL,
}) => {
  const paths = [
    "/docs",
    "/redoc",
    "/openapi.json",
    "/healthz",
    "/readyz",
    "/metrics",
    "/api/docs",
    "/api/openapi.json",
    "/api/readyz",
  ];
  for (const path of paths) {
    expect((await request.get(path)).status(), `GET ${path}`).toBe(404);
  }
  // The reset route exists since R2 (U-web-settings-45): GET is refused, and POST needs a session.
  expect((await request.get("/api/settings/reset")).status(), "GET /api/settings/reset").toBe(405);
  const post = await request.post("/api/settings/reset", {
    data: { version: 0 },
    headers: { Origin: baseURL ?? PUBLIC_ORIGIN },
  });
  expect(post.status(), "POST /api/settings/reset without a session").toBe(401);

  const secure = await request.get("/login");
  expect(secure.headers()["strict-transport-security"]).toBe("max-age=31536000");

  const plain = await request.get("http://127.0.0.1:8081/settings", { maxRedirects: 0 });
  expect([301, 308]).toContain(plain.status());
  expect(plain.headers()["location"]).toBe(`${baseURL ?? PUBLIC_ORIGIN}/settings`);
});

// 8 (AC-28)
test("a time zone change shows its preview, then the saved banner with the real notice interval and the last-change line", async ({
  page,
}) => {
  seedSettings();
  await signIn(page);
  const session = (await (await page.request.get("/api/session")).json()) as { noticeIntervalMinutes: number };
  const minutes = session.noticeIntervalMinutes;

  await page.getByRole("combobox", { name: "Time zone" }).fill("Bangkok");
  await page.getByRole("option", { name: /Bangkok/ }).first().click();

  await expect(page.getByText(/^Quiet hours will now be 23:00 to 07:00 Bangkok time \(.* Amsterdam time\)\.$/)).toBeVisible();

  await page.getByRole("button", { name: "Save changes" }).click();

  const banner = page.getByRole("status").filter({ hasText: /Saved at \d{2}:\d{2}\./ });
  await expect(banner).toContainText("Quiet hours are 23:00 to 07:00 (Bangkok time).");
  await expect(banner).toContainText(`within about ${String(minutes)} ${minutes === 1 ? "minute" : "minutes"}.`);
  await expect(page.getByText(/^Last changed from the web at \d{2}:\d{2}$/)).toBeVisible();
  expect(storedRow()).toBe("2|1080|Asia/Bangkok");
});

// 9 (AC-22)
for (const viewport of [
  { width: 375, height: 812 },
  { width: 1280, height: 800 },
]) {
  test(`axe finds no violation on the sign-in and settings pages at ${String(viewport.width)} px`, async ({ page }) => {
    seedSettings();
    await page.setViewportSize(viewport);
    await page.goto("/login");
    await settle(page);
    expect(await axeProblems(page), "username step").toEqual([]);

    const code = await askForCode(page);
    await settle(page);
    expect(await axeProblems(page), "code step").toEqual([]);

    await page.getByLabel("Code", { exact: true }).fill(code);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
    await expect(page.getByText(/^Last changed from/)).toBeVisible();
    await settle(page);
    expect(await axeProblems(page), "settings").toEqual([]);
  });
}

// 10 (AC-27)
test("a locked web refuses the signed-in user and answers a right code exactly like a wrong one", async ({
  page,
  request,
  browser,
  baseURL,
}) => {
  seedSettings();
  await signIn(page);
  lockWeb();

  expect((await page.request.get("/api/settings")).status()).toBe(401);

  const headers = { Origin: baseURL ?? PUBLIC_ORIGIN };
  await respectCooldown();
  const asked = await request.post("/auth/request-code", { data: { username: USERNAME }, headers });
  lastAsk = Date.now();
  expect(asked.status()).toBe(200);
  await expect.poll(async () => newestCode().catch(() => ""), { timeout: 30_000 }).toMatch(SIX_DIGITS);
  const code = await newestCode();
  const locked = await request.post("/auth/verify-code", { data: { code }, headers });

  // The reference: a wrong code from a browser that holds a live login request (a decoy of an unknown username). While
  // the lock is set the owner's request is stored like that one, so the lock leaves no trace (U-web-settings-69).
  const stranger = await browser.newContext(baseURL ? { baseURL } : {});
  const decoy = await stranger.request.post("/auth/request-code", { data: { username: "somebody-else" }, headers });
  expect(decoy.status()).toBe(200);
  const reference = await stranger.request.post("/auth/verify-code", { data: { code: "000000" }, headers });

  expect(locked.status()).toBe(400);
  expect(locked.status()).toBe(reference.status());
  expect(await locked.text()).toBe(await reference.text());
  const shown = (name: string, answer: typeof locked): string[] =>
    answer
      .headersArray()
      .filter((header) => header.name.toLowerCase() === name)
      .map((header) => header.value);
  expect(shown("content-type", locked)).toEqual(shown("content-type", reference));
  expect(shown("set-cookie", locked)).toEqual(shown("set-cookie", reference));
  expect(shown("set-cookie", locked).join(" ")).not.toContain("__Host-session=");
  await stranger.close();
});
