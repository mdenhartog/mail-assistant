import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";

import { held, MASKED, reply, sequence, STORED, stubApi } from "./stubs";
import type { Handler, Handlers } from "./stubs";

/** One screen state of the web app, reached the way a person reaches it, against stubbed answers. */
export interface UiState {
  name: string;
  /**
   * Opens the page, drives it to the state and waits until the state is on screen. Returns a function that
   * releases a request the state holds back (loading, sending, saving), so the page can end cleanly.
   */
  open: (page: Page) => Promise<() => void>;
}

const NOTHING_HELD = (): void => undefined;

function state(name: string, reach: (page: Page) => Promise<unknown>): UiState {
  return {
    name,
    open: async (page) => {
      const release = await reach(page);
      return typeof release === "function" ? (release as () => void) : NOTHING_HELD;
    },
  };
}

const CODE_SENT = reply(200, { maskedAddress: MASKED, expiresAt: "2026-11-12T12:10:00Z", resendAfterSeconds: 60 });
const WRONG = { detail: "That code is not right.", attemptsLeft: 3 };
const QUIET_CLASH = {
  problems: [
    { field: "overviewAt", rule: "overview_in_quiet_hours", value: "23:30", example: "For example 18:00" },
    { field: "remindAt", rule: "remind_in_quiet_hours", value: "06:00", example: "For example 09:00" },
  ],
};
const TELEGRAM_NOW = {
  updatedAt: "2026-11-12T13:02:00Z",
  updatedVia: "telegram",
  version: 4,
  values: { ...STORED.values, overviewAt: "19:30", remindAt: "10:00" },
};

async function toCodeStep(page: Page, handlers: Handlers = {}): Promise<void> {
  await stubApi(page, handlers);
  await page.goto("/login");
  await page.getByLabel("Username").fill("marco");
  await page.getByRole("button", { name: "Send me a code" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Enter your code" })).toBeVisible();
}

async function submitCode(page: Page): Promise<void> {
  await page.getByLabel("Code").fill("123456");
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function toLoadedSettings(page: Page, handlers: Handlers = {}): Promise<void> {
  await stubApi(page, { signedIn: true, ...handlers });
  await page.goto("/settings");
  await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
  await expect(page.getByLabel("Daily overview")).toBeVisible();
}

async function toDirtySettings(page: Page, handlers: Handlers = {}): Promise<void> {
  await toLoadedSettings(page, handlers);
  await page.getByLabel("Remind-me-later default").fill("10:30");
  await expect(page.getByRole("button", { name: "Save changes" })).toBeEnabled();
}

/** The typed values of a session that ended, as the page keeps them in this tab (D-6). */
async function keepDraft(page: Page): Promise<void> {
  await page.addInitScript(
    ([key, values, version]) => {
      window.sessionStorage.setItem(key, JSON.stringify({ values, version, savedAt: Date.now() }));
    },
    ["settings-draft", { ...STORED.values, remindAt: "10:30" }, STORED.version] as const,
  );
}

function loginStates(): UiState[] {
  const resend = (answer: Handler): Handlers => ({ requestCode: sequence(CODE_SENT, answer) });
  return [
    state("login: step 1", async (page) => {
      await stubApi(page);
      await page.goto("/login");
      await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
      await expect(page.getByLabel("Username")).toBeVisible();
    }),
    state("login: sending", async (page) => {
      const gate = held(CODE_SENT);
      await stubApi(page, { requestCode: gate.handler });
      await page.goto("/login");
      await page.getByLabel("Username").fill("marco");
      await page.getByRole("button", { name: "Send me a code" }).click();
      await expect(page.getByRole("button", { name: "Sending..." })).toBeVisible();
      return gate.release;
    }),
    state("login: step 2", (page) => toCodeStep(page)),
    state("login: wrong code", async (page) => {
      await toCodeStep(page, { verifyCode: reply(400, WRONG) });
      await submitCode(page);
      await expect(page.getByText("That code is not right. You have 3 tries left.")).toBeVisible();
    }),
    state("login: expired code", async (page) => {
      await page.clock.install();
      await toCodeStep(page, { verifyCode: reply(400, { detail: "That code is not right." }) });
      await page.clock.fastForward("11:00");
      await submitCode(page);
      await expect(page.getByText("This code has expired.")).toBeVisible();
    }),
    state("login: too many tries", async (page) => {
      await toCodeStep(page, { verifyCode: reply(400, { ...WRONG, attemptsLeft: 0 }) });
      await submitCode(page);
      await expect(page.getByText("Too many wrong tries.")).toBeVisible();
    }),
    state("login: cooldown", async (page) => {
      await page.clock.install();
      await toCodeStep(page, resend(reply(429, { detail: "Wait" }, { "Retry-After": "41" })));
      await page.clock.fastForward("01:01");
      await expect(page.getByRole("button", { name: "Send a new code" })).toBeEnabled();
      await page.getByRole("button", { name: "Send a new code" }).click();
      await expect(page.getByText("Please wait before asking for another code.")).toBeVisible();
    }),
    state("login: hourly cap", async (page) => {
      await page.clock.install();
      await toCodeStep(page, resend(reply(429, { detail: "Wait" }, { "Retry-After": "1500" })));
      await page.clock.fastForward("01:01");
      await expect(page.getByRole("button", { name: "Send a new code" })).toBeEnabled();
      await page.getByRole("button", { name: "Send a new code" }).click();
      await expect(page.getByText("You have asked for too many codes this hour.")).toBeVisible();
    }),
    state("login: session expired", async (page) => {
      await stubApi(page);
      await page.goto("/login?notice=expired");
      await expect(page.getByText("Your session ended.")).toBeVisible();
    }),
    state("login: session expired, typed values kept", async (page) => {
      await keepDraft(page);
      await stubApi(page);
      await page.goto("/login?notice=expired");
      await expect(page.getByText(/what you typed is kept/)).toBeVisible();
    }),
  ];
}

function settingsStates(): UiState[] {
  return [
    state("settings: loading", async (page) => {
      const gate = held(reply(200, STORED));
      await stubApi(page, { signedIn: true, getSettings: gate.handler });
      await page.goto("/settings");
      await expect(page.getByText("Loading your settings")).toBeVisible();
      return gate.release;
    }),
    state("settings: loaded", (page) => toLoadedSettings(page)),
    state("settings: dirty", (page) => toDirtySettings(page)),
    state("settings: zone options open", async (page) => {
      await toLoadedSettings(page);
      await page.getByRole("combobox", { name: "Time zone" }).fill("Ban");
      await expect(page.getByRole("listbox")).toBeVisible();
    }),
    state("settings: saving", async (page) => {
      const gate = held(reply(200, { ...STORED, version: 4 }));
      await toDirtySettings(page, { putSettings: gate.handler });
      await page.getByRole("button", { name: "Save changes" }).click();
      await expect(page.getByRole("button", { name: "Saving..." })).toBeVisible();
      return gate.release;
    }),
    state("settings: saved", async (page) => {
      await toDirtySettings(page);
      await page.getByRole("button", { name: "Save changes" }).click();
      await expect(page.getByText(/^Saved at/)).toBeVisible();
    }),
    state("settings: validation error", async (page) => {
      await toDirtySettings(page, { putSettings: reply(422, QUIET_CLASH) });
      await page.getByRole("button", { name: "Save changes" }).click();
      await expect(page.getByText(/would fall inside quiet hours/).first()).toBeVisible();
    }),
    state("settings: save failed", async (page) => {
      await toDirtySettings(page, { putSettings: reply(500) });
      await page.getByRole("button", { name: "Save changes" }).click();
      await expect(page.getByText("Could not save. Nothing was changed.")).toBeVisible();
    }),
    state("settings: conflict", async (page) => {
      await toDirtySettings(page, { putSettings: reply(409, { current: TELEGRAM_NOW }) });
      await page.getByRole("button", { name: "Save changes" }).click();
      await expect(page.getByText(/Settings changed in Telegram/)).toBeVisible();
    }),
    state("settings: typed values restored", async (page) => {
      await keepDraft(page);
      await toLoadedSettings(page);
      await expect(page.getByText("Welcome back.")).toBeVisible();
      await expect(page.getByLabel("Remind-me-later default")).toHaveValue("10:30");
    }),
    state("settings: load failed", async (page) => {
      await stubApi(page, { signedIn: true, getSettings: reply(500) });
      await page.goto("/settings");
      await expect(page.getByText("Could not load your settings.")).toBeVisible();
    }),
    state("settings: session expired", async (page) => {
      await toDirtySettings(page, {
        putSettings: async (route, call) => {
          call.state.signedIn = false;
          await reply(401, { detail: "No session" })(route, call);
        },
      });
      await page.getByRole("button", { name: "Save changes" }).click();
      await expect(page.getByText("Your session ended.")).toBeVisible();
    }),
  ];
}

function otherStates(): UiState[] {
  return [
    state("refused (403)", async (page) => {
      await stubApi(page, { signedIn: true, getSettings: reply(403, { detail: "Forbidden" }) });
      await page.goto("/settings");
      await expect(page.getByText("This request was not allowed.")).toBeVisible();
    }),
    state("not found", async (page) => {
      await stubApi(page);
      await page.goto("/no-such-page");
      await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
    }),
  ];
}

/** Every state of AC-22: the login page, the settings page and the two error pages. */
export function allStates(): UiState[] {
  return [...loginStates(), ...settingsStates(), ...otherStates()];
}
