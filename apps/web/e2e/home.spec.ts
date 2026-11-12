import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// The api image still runs the health-only app (U-web-settings-38 swaps it), so /api/session cannot answer 401 yet;
// /login shows the sign-in page whatever the session lookup says.
test("the sign-in page shows its heading", async ({ page }) => {
  await page.goto("/login");

  await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
});

test("home has no serious accessibility violations", async ({ page }) => {
  await page.goto("/");

  const results = await new AxeBuilder({ page }).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => v.id)).toEqual([]);
});

test("home is served with security headers", async ({ page }) => {
  const response = await page.goto("/");
  const headers = response?.headers() ?? {};

  expect(headers["content-security-policy"]).toContain("default-src 'self'");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
});

test("no tokens are kept in localStorage", async ({ page }) => {
  await page.goto("/");

  const keys = await page.evaluate(() => Object.keys(window.localStorage));
  expect(keys.filter((k) => /token/i.test(k))).toEqual([]);
});
