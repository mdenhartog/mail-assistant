import { expect, test as setup } from "@playwright/test";

import { clearMailbox, newestCode } from "./support/mailbox";
import { STORAGE_STATE, USERNAME } from "./support/session";

// Signs in once through the real login page of the prod-like stack: the username, the code the api mailed to the
// catcher, "Sign in". The state it saves (the `__Host-session` cookie) is reused by the projects that depend on it
// (AC-3, AC-7). The test account is the stack's allowed user from compose; no real credentials exist here.
setup("sign in with the code from the mail catcher", async ({ page }) => {
  await clearMailbox();

  await page.goto("/login");
  await page.getByLabel("Username").fill(USERNAME);
  await page.getByRole("button", { name: "Send me a code" }).click();

  await expect
    .poll(async () => newestCode().catch(() => ""), { message: "the sign-in mail arrives", timeout: 30_000 })
    .toMatch(/^\d{6}$/);
  await page.getByLabel("Code", { exact: true }).fill(await newestCode());
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
  await page.context().storageState({ path: STORAGE_STATE });
});
