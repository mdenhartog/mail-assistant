// Signs in through the real login page of the prod-like stack for the specs whose reset removes the sessions
// (journey, categories): the username, the code the api mailed to the catcher, "Sign in". The api asks for a pause
// between two codes (the prod-like stack sets one second), so the helper waits for it.
import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";

import { clearMailbox, newestCode } from "./mailbox";
import { USERNAME } from "./session";

const SIX_DIGITS = /^\d{6}$/;
const COOLDOWN_MS = 1_300;

let lastAsk = 0;

async function respectCooldown(): Promise<void> {
  await expect
    .poll(() => Date.now() - lastAsk, { intervals: [100], timeout: COOLDOWN_MS + 1_000 })
    .toBeGreaterThanOrEqual(COOLDOWN_MS);
}

/** Signs in and lands on the settings page; the page then holds a live session. */
export async function signInThroughPage(page: Page): Promise<void> {
  await respectCooldown();
  await clearMailbox();
  await page.goto("/login");
  await page.getByLabel("Username").fill(USERNAME);
  await page.getByRole("button", { name: "Send me a code" }).click();
  lastAsk = Date.now();
  await expect
    .poll(async () => newestCode().catch(() => ""), { message: "the sign-in mail arrives", timeout: 30_000 })
    .toMatch(SIX_DIGITS);
  await page.getByLabel("Code", { exact: true }).fill(await newestCode());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/settings$/);
}
