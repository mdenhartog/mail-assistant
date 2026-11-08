import { defineConfig, devices } from "@playwright/test";

// E2E runs against the prod-like stack (docker compose --profile prod-like) or a PR preview.
export default defineConfig({
  testDir: "./e2e",
  testIgnore: ["**/*.gxp.spec.ts"], // GAMP 5 scenarios run via playwright.gxp.config.ts
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["github"]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    { name: "mobile", use: { ...devices["Pixel 7"] } },
    { name: "tablet", use: { ...devices["Galaxy Tab S9"] } },
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
  ],
});
