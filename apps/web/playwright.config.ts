import { defineConfig, devices } from "@playwright/test";

import { STORAGE_STATE } from "./e2e/support/session";

// E2E runs against the prod-like TLS edge (docker compose --profile prod-like, after deploy/prod-like/certs.sh) or a PR
// preview. The browser must trust deploy/prod-like/certs/ca.crt (certificate checks stay on).
//
// `setup` signs in once through the real login page (the code is read from the mail catcher) and saves the session.
// `smoke-375` and `smoke-1280` start from that state, one after the other because both save the one settings row.
// The three viewport projects have no session: they check the public page, the headers and the mailbox helper.
// `journey` (U-web-settings-43) is the release gate: one worker, in file order, and only after every project above, because
// it resets the one settings row and the sign-in tables by owner SQL and empties the one mailbox. It exists only in the
// prod-like job (it needs `docker compose exec` into the stack's database); each test signs in for itself.
const SMOKE = /smoke\.spec\.ts/;
const GXP = "**/*.gxp.spec.ts"; // GAMP 5 scenarios run via playwright.gxp.config.ts
const UI_STATES = /ui-states\.spec\.ts/;
const JOURNEY = /journey\.spec\.ts/;

// `ui-states` renders every login and settings state against a stubbed API (route.fulfill, no backend, no setup)
// on a local preview of the built app. The web job runs it with `--project=ui-states`; the prod-like job sets
// E2E_BASE_URL, which leaves this project and its preview server out.
const UI_STATES_URL = "http://127.0.0.1:4173";
const stubbed = process.env.E2E_BASE_URL === undefined;

export default defineConfig({
  testDir: "./e2e",
  testIgnore: [GXP],
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
    { name: "setup", testMatch: /setup\.ts/, use: { ...devices["Desktop Chrome"] } },
    {
      name: "smoke-375",
      testMatch: SMOKE,
      dependencies: ["setup"],
      use: { ...devices["Desktop Chrome"], viewport: { width: 375, height: 812 }, storageState: STORAGE_STATE },
    },
    {
      name: "smoke-1280",
      testMatch: SMOKE,
      dependencies: ["smoke-375"],
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 }, storageState: STORAGE_STATE },
    },
    { name: "mobile", testIgnore: [GXP, SMOKE, UI_STATES, JOURNEY], dependencies: ["setup"], use: { ...devices["Pixel 7"] } },
    { name: "tablet", testIgnore: [GXP, SMOKE, UI_STATES, JOURNEY], dependencies: ["setup"], use: { ...devices["Galaxy Tab S9"] } },
    {
      name: "desktop",
      testIgnore: [GXP, SMOKE, UI_STATES, JOURNEY],
      dependencies: ["setup"],
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    ...(stubbed
      ? []
      : [
          {
            name: "journey",
            testMatch: JOURNEY,
            fullyParallel: false,
            dependencies: ["setup", "smoke-1280", "mobile", "tablet", "desktop"],
            use: { ...devices["Desktop Chrome"] },
          },
        ]),
    ...(stubbed
      ? [{ name: "ui-states", testMatch: UI_STATES, use: { ...devices["Desktop Chrome"], baseURL: UI_STATES_URL } }]
      : []),
  ],
  ...(stubbed
    ? {
        webServer: {
          command: "pnpm exec vite build && pnpm exec vite preview --host 127.0.0.1 --port 4173 --strictPort",
          url: UI_STATES_URL,
          reuseExistingServer: !process.env.CI,
          timeout: 180_000,
        },
      }
    : {}),
});
