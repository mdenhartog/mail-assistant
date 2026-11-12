import { expect, test } from "@playwright/test";

// One pass over the real stack at 375 and 1280 px (projects `smoke-375` and `smoke-1280`, one after the other because
// both save the one settings row): the signed-in user opens /settings over HTTPS, sees the stored values, saves a
// valid change and sees it again after a reload (AC-1, AC-9). Nothing else is asserted here; `journey` does the rest.
test("settings opens with the stored values, a valid change is saved and survives a reload", async ({ page }) => {
  await page.goto("/settings");

  await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
  const overview = page.getByLabel("Daily overview", { exact: true });
  await expect(overview).toHaveValue(/^\d{2}:\d{2}$/);
  // The quiet hours are never touched by this test, so they are the defaults of a fresh stack in both viewports.
  await expect(page.getByLabel("From", { exact: true })).toHaveValue("23:00");
  await expect(page.getByLabel("Until", { exact: true })).toHaveValue("07:00");

  // Whatever the other viewport saved first, move the overview to the other of two times.
  const next = (await overview.inputValue()) === "18:30" ? "18:00" : "18:30";
  await overview.fill(next);
  await page.getByRole("button", { name: "Save changes" }).click();

  await expect(page.getByRole("button", { name: "Save changes" })).toBeDisabled(); // clean again: the save landed
  await page.reload();

  await expect(page.getByLabel("Daily overview", { exact: true })).toHaveValue(next);
  await expect(page.getByLabel("From", { exact: true })).toHaveValue("23:00");
});

test("the settings page is not served to a browser without the saved session", async ({ browser, baseURL }) => {
  const anonymous = await browser.newContext({
    ...(baseURL ? { baseURL } : {}),
    storageState: { cookies: [], origins: [] },
  });
  const page = await anonymous.newPage();

  await page.goto("/settings");

  await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
  await anonymous.close();
});
