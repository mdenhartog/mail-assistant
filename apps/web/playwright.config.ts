import { defineConfig, devices } from "@playwright/test";
import type { PlaywrightTestConfig } from "@playwright/test";

// `ui-states` renders every login and settings state against a stubbed API (route.fulfill, no backend) on a
// local preview of the built app. It runs when no edge is given; the prod-like jobs set E2E_BASE_URL and skip it.
const UI_STATES_URL = "http://127.0.0.1:4173";
const uiStates: PlaywrightTestConfig["projects"] = process.env.E2E_BASE_URL
  ? []
  : [
      {
        name: "ui-states",
        testMatch: "**/ui-states.spec.ts",
        testIgnore: ["**/*.gxp.spec.ts"],
        use: { ...devices["Desktop Chrome"], baseURL: UI_STATES_URL },
      },
    ];

// E2E runs against the prod-like TLS edge (docker compose --profile prod-like, after deploy/prod-like/certs.sh) or a PR
// preview. The browser must trust deploy/prod-like/certs/ca.crt (certificate checks stay on).
export default defineConfig({
  testDir: "./e2e",
  testIgnore: ["**/*.gxp.spec.ts", "**/ui-states.spec.ts"], // GAMP 5 scenarios run via playwright.gxp.config.ts
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["github"]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "https://mail-assistant.localhost:8443",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    { name: "mobile", use: { ...devices["Pixel 7"] } },
    { name: "tablet", use: { ...devices["Galaxy Tab S9"] } },
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    ...uiStates,
  ],
  ...(process.env.E2E_BASE_URL
    ? {}
    : {
        webServer: {
          command: "pnpm exec vite build && pnpm exec vite preview --host 127.0.0.1 --port 4173 --strictPort",
          url: UI_STATES_URL,
          reuseExistingServer: !process.env.CI,
          timeout: 180_000,
        },
      }),
});
