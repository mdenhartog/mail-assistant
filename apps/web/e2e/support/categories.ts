import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";

import { CATEGORIES, held, reply, stubApi } from "./stubs";
import type { Handlers } from "./stubs";
import type { UiState } from "./states";

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

async function toLoaded(page: Page, handlers: Handlers = {}): Promise<void> {
  await stubApi(page, { signedIn: true, ...handlers });
  await page.goto("/categories");
  await expect(page.getByRole("heading", { level: 1, name: "Categories" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit Invoices", exact: true })).toBeVisible();
}

async function toSummary(page: Page, handlers: Handlers = {}): Promise<void> {
  await toLoaded(page, handlers);
  await page.getByRole("button", { name: "Edit Invoices", exact: true }).click();
  await page.getByLabel("Name").fill("Bills");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("alertdialog", { name: /^Save \d+ changes?\?$/ })).toBeVisible();
}

async function toSaved(page: Page, handlers: Handlers = {}): Promise<void> {
  await toSummary(page, handlers);
  await page.getByRole("alertdialog").getByRole("button", { name: "Save changes" }).click();
}

const CONFLICT = {
  type: "about:blank",
  title: "Conflict",
  status: 409,
  reason: "version",
  current: { ...CATEGORIES, version: 6 },
};

/** The states of the Categories page (AC-23); the same checks run on them as on the login and settings states. */
export function categoriesStates(): UiState[] {
  return [
    state("categories: loading", async (page) => {
      const gate = held(reply(200, CATEGORIES));
      await stubApi(page, { signedIn: true, getCategories: gate.handler });
      await page.goto("/categories");
      await expect(page.getByText("Loading your categories")).toBeVisible();
      return gate.release;
    }),
    state("categories: loaded", (page) => toLoaded(page)),
    state("categories: not ready", async (page) => {
      await stubApi(page, { signedIn: true, getCategories: reply(200, { ...CATEGORIES, version: 0, ready: false, categories: [] }) });
      await page.goto("/categories");
      await expect(page.getByText("Your categories are still being set up.")).toBeVisible();
    }),
    state("categories: load failed", async (page) => {
      await stubApi(page, { signedIn: true, getCategories: reply(500) });
      await page.goto("/categories");
      await expect(page.getByText("Could not load your categories.")).toBeVisible();
    }),
    state("categories: errors by the fields", async (page) => {
      await toLoaded(page);
      await page.getByRole("button", { name: "Add category" }).click();
      await page.getByRole("button", { name: "Save", exact: true }).click();
      await expect(page.getByText("Give the category a name.")).toBeVisible();
    }),
    state("categories: save summary", (page) => toSummary(page)),
    state("categories: saving", async (page) => {
      const gate = held(reply(200, { ...CATEGORIES, version: 6 }));
      await toSaved(page, { putCategories: gate.handler });
      await expect(page.getByRole("button", { name: "Saving..." })).toBeVisible();
      return gate.release;
    }),
    state("categories: saved", async (page) => {
      await toSaved(page);
      await expect(page.getByText("Saved.")).toBeVisible();
    }),
    state("categories: conflict", async (page) => {
      await toSaved(page, { putCategories: reply(409, CONFLICT) });
      await expect(page.getByText("The list changed somewhere else.")).toBeVisible();
    }),
    state("categories: too many saves", async (page) => {
      await toSaved(page, { putCategories: reply(429, undefined, { "Retry-After": "60" }) });
      await expect(page.getByText("Too many saves.")).toBeVisible();
    }),
    state("categories: save failed", async (page) => {
      await toSaved(page, { putCategories: reply(500) });
      await expect(page.getByText("Could not save. Nothing was changed.")).toBeVisible();
    }),
  ];
}
