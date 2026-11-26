import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";

import { CATEGORIES, held, NO_PLAN, reply, stubApi } from "./stubs";
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

const HASH = "a".repeat(64);
const LONG = `Assistant/${"W".repeat(60)}`;
/** Untrusted label text: markup and a link inside it must stay text. */
const MARKUP = 'Assistant/<a href="https://evil.example">x</a>';
const ITEMS = [
  { id: "id-1", oldName: "Assistant/Amerika", newName: "Amerika", mailCount: 40, action: "merge", itemState: "planned" },
  { id: "id-2", oldName: LONG, newName: "W".repeat(60), mailCount: 12, action: "rename", itemState: "planned" },
  { id: "id-3", oldName: MARKUP, newName: "Travel", mailCount: 3, action: "rename", itemState: "planned" },
];
const SUMMARY = { labels: 3, mails: 55 };
const PENDING = { state: "pending", planHash: HASH, items: ITEMS, summary: SUMMARY };
const CONFIRMED = { ...PENDING, state: "confirmed" };
const DONE = {
  state: "done",
  planHash: HASH,
  items: ITEMS.map((item, index) => ({ ...item, itemState: index === 2 ? "skipped" : "done" })),
  summary: SUMMARY,
};
const DELETED = {
  retentionDays: 30,
  items: [
    { name: "Assistant/Newer", deletedAt: "2026-11-24T12:00:00Z" },
    { name: LONG, deletedAt: "2026-11-20T12:00:00Z" },
  ],
};

async function toLoaded(page: Page, handlers: Handlers = {}): Promise<void> {
  await stubApi(page, { signedIn: true, getPlan: reply(200, NO_PLAN), ...handlers });
  await page.goto("/categories");
  await expect(page.getByRole("heading", { level: 1, name: "Categories" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Sort everything again" })).toBeVisible();
}

async function toPending(page: Page, handlers: Handlers = {}): Promise<void> {
  await toLoaded(page, { getRename: reply(200, PENDING), ...handlers });
  await expect(page.getByText("3 labels, 55 mails")).toBeVisible();
}

async function toDialog(page: Page, handlers: Handlers = {}): Promise<void> {
  await toPending(page, handlers);
  await page.getByRole("button", { name: "Rename these labels" }).click();
  await expect(page.getByRole("alertdialog", { name: "Rename 3 labels?" })).toBeVisible();
}

async function confirm(page: Page, handlers: Handlers = {}): Promise<void> {
  await toDialog(page, handlers);
  await page.getByRole("alertdialog").getByRole("textbox").fill("RENAME");
  await page.getByRole("alertdialog").getByRole("button", { name: "Rename labels" }).click();
}

/** The rename section and the recently deleted list, in every state a person can reach. */
export function renameStates(): UiState[] {
  return [
    state("rename: first run, no list", async (page) => {
      await toLoaded(page, { getCategories: reply(200, { ...CATEGORIES, categories: [], other: { mailCount: 0 } }) });
      await expect(page.getByText("Load your YAML file first: the list is no longer read from Gmail.")).toBeVisible();
    }),
    state("rename: loading", async (page) => {
      const gate = held(reply(200, PENDING));
      await stubApi(page, { signedIn: true, getPlan: reply(200, NO_PLAN), getRename: gate.handler });
      await page.goto("/categories");
      await expect(page.getByText("Loading the rename preview")).toBeVisible();
      return gate.release;
    }),
    state("rename: preview failed", async (page) => {
      await toLoaded(page, { getRename: reply(500) });
      await expect(page.getByText("Could not load the rename preview.")).toBeVisible();
    }),
    state("rename: pending preview", (page) => toPending(page)),
    state("rename: confirmation dialog", (page) => toDialog(page)),
    state("rename: confirmation mismatch", async (page) => {
      await toDialog(page);
      await page.getByRole("alertdialog").getByRole("textbox").fill("7");
      await page.getByRole("alertdialog").getByRole("button", { name: "Rename labels" }).click();
      await expect(page.getByRole("alertdialog").getByRole("alert")).toBeVisible();
    }),
    state("rename: sending", async (page) => {
      const gate = held(reply(201, { confirmationId: "5b0c1c2e-1b1e-4c52-9d0e-0a6a1b1c00cc" }));
      await confirm(page, { postRenameConfirmation: gate.handler });
      await expect(page.getByRole("button", { name: "Sending..." })).toBeVisible();
      return gate.release;
    }),
    state("rename: plan changed", async (page) => {
      await confirm(page, { postRenameConfirmation: reply(409, { detail: "x" }) });
      await expect(page.getByText("The plan changed.")).toBeVisible();
    }),
    state("rename: in progress", async (page) => {
      await toLoaded(page, { getRename: reply(200, CONFIRMED) });
      await expect(page.getByRole("status", { name: "Renaming is in progress" })).toBeVisible();
    }),
    state("rename: result", async (page) => {
      await toLoaded(page, { getRename: reply(200, DONE) });
      await expect(page.getByRole("region", { name: "Renaming finished" })).toBeVisible();
    }),
    state("rename: restore dialog", async (page) => {
      await toLoaded(page, { getRename: reply(200, DONE) });
      await page.getByRole("button", { name: "Restore the old names" }).click();
      await expect(page.getByRole("alertdialog", { name: "Restore the old names?" })).toBeVisible();
    }),
    state("rename: restore requested", async (page) => {
      await toLoaded(page, { getRename: reply(200, DONE) });
      await page.getByRole("button", { name: "Restore the old names" }).click();
      await page.getByRole("alertdialog").getByRole("button", { name: "Restore names" }).click();
      await expect(page.getByRole("status").filter({ hasText: "The old names are being restored." })).toBeFocused();
    }),
    state("rename: recently deleted", async (page) => {
      await toLoaded(page, { getDeleted: reply(200, DELETED) });
      await expect(page.getByRole("region", { name: "Recently deleted labels" }).getByRole("listitem")).toHaveCount(2);
    }),
    state("rename: recently deleted failed", async (page) => {
      await toLoaded(page, { getDeleted: reply(500) });
      await expect(page.getByText("Could not load the recently deleted labels.")).toBeVisible();
    }),
  ];
}
