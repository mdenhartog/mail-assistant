import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";

import { CATEGORIES, held, NO_PLAN, PLAN, reply, stubApi, UPLOAD_PREVIEW } from "./stubs";
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
  await stubApi(page, { signedIn: true, getPlan: reply(200, NO_PLAN), ...handlers });
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

const PROBLEMS = {
  type: "about:blank",
  title: "Unprocessable content",
  status: 422,
  problems: [
    { rule: "unknown_field", line: 4, field: "categories[0].colour", message: "This field is not part of the format." },
    { rule: "empty_segment", line: 9, field: "categories[1].name", message: "A name cannot have an empty part." },
  ],
};

async function toUploaded(page: Page, handlers: Handlers = {}): Promise<void> {
  await toLoaded(page, handlers);
  await page.getByLabel("Choose a YAML file").setInputFiles({ name: "mail-categories.yaml", mimeType: "application/yaml", buffer: Buffer.from("schema: 1\n") });
}

async function toReplaced(page: Page, handlers: Handlers = {}): Promise<void> {
  await toUploaded(page, handlers);
  await page.getByRole("button", { name: "Replace my whole list (2 removed)" }).click();
  await expect(page.getByText("Your list was replaced.")).toBeVisible();
}

async function toSortAgain(page: Page, handlers: Handlers = {}): Promise<void> {
  await toLoaded(page, handlers);
  await expect(page.getByRole("textbox", { name: "Confidence threshold (%)" })).toBeVisible();
}

/** The states of the sort-again controls (AC-45, AC-46, AC-68). */
function sortAgainStates(): UiState[] {
  return [
    state("categories: sort again", (page) => toSortAgain(page)),
    state("categories: sort again, loading", async (page) => {
      const gate = held(reply(200, { threshold: 50 }));
      await stubApi(page, { signedIn: true, getPlan: reply(200, NO_PLAN), getLatestResort: gate.handler });
      await page.goto("/categories");
      await expect(page.getByText("Loading the threshold")).toBeVisible();
      return gate.release;
    }),
    state("categories: sort again, load failed", async (page) => {
      await toLoaded(page, { getLatestResort: reply(500) });
      await expect(page.getByText("Could not load the threshold.")).toBeVisible();
    }),
    state("categories: sort again, later visit", async (page) => {
      await toLoaded(page, { getLatestResort: reply(200, { threshold: 85 }) });
      await expect(page.getByRole("textbox", { name: "Confidence threshold (%)" })).toHaveValue("85");
    }),
    state("categories: sort again, refused threshold", async (page) => {
      await toSortAgain(page);
      await page.getByRole("textbox", { name: "Confidence threshold (%)" }).fill("49");
      await page.getByRole("button", { name: "Sort everything again" }).click();
      await expect(page.getByText("Use a whole number from 50 to 100.")).toBeVisible();
    }),
    state("categories: sort again, plan open", async (page) => {
      await toLoaded(page, { getPlan: reply(200, PLAN) });
      await expect(page.getByText(/A plan is open\./)).toBeVisible();
    }),
    state("categories: sort again, requested", async (page) => {
      await toSortAgain(page);
      await page.getByRole("button", { name: "Sort everything again" }).click();
      await expect(page.getByText(/Your request is in/)).toBeVisible();
    }),
    state("categories: sort again, request refused", async (page) => {
      await toLoaded(page, { postResort: reply(409) });
      await page.getByRole("button", { name: "Sort everything again" }).click();
      await expect(page.getByText(/already open or being prepared/)).toBeVisible();
    }),
    state("categories: archive label refused", async (page) => {
      const problem = { type: "about:blank", title: "Unprocessable content", status: 422, problems: [{ rule: "archive_system_label", field: "archive_label", index: null, position: null, otherIndex: null }] };
      await toLoaded(page, { putCategories: reply(422, problem, { "Content-Type": "application/problem+json" }) });
      await page.getByLabel("Archive label").fill("INBOX");
      await page.getByRole("button", { name: "Save changes" }).click();
      await page.getByRole("alertdialog").getByRole("button", { name: "Save changes" }).click();
      await expect(page.getByText("This is a Gmail label of its own and cannot be your archive label.")).toBeVisible();
    }),
  ];
}

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
    state("categories: edit view with skipped counts", async (page) => {
      const senders = [
        { entry: "billing@example.com", subdomains: false, skippedCount: 3 },
        { entry: "a-very-long-sender-name-without-any-break@a-very-long-domain-name-that-keeps-going.example.com", subdomains: true, skippedCount: 1 },
        { entry: "quiet@example.com", subdomains: false, skippedCount: 0 },
      ];
      const [invoices, ...rest] = CATEGORIES.categories;
      await toLoaded(page, { getCategories: reply(200, { ...CATEGORIES, categories: [{ ...invoices, senders }, ...rest] }) });
      await page.getByRole("button", { name: "Edit Invoices", exact: true }).click();
      await expect(page.getByText("Not applied 3 times: Gmail could not confirm the sender")).toBeVisible();
      await expect(page.getByText("Not applied 1 time: Gmail could not confirm the sender")).toBeVisible();
      await expect(page.getByText("The AI judged those mails instead.")).toBeVisible();
    }),
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
    state("categories: upload preview", async (page) => {
      await toUploaded(page);
      await expect(page.getByRole("heading", { name: "Preview of your file" })).toBeFocused();
    }),
    state("categories: upload checking", async (page) => {
      const gate = held(reply(200, UPLOAD_PREVIEW));
      await toUploaded(page, { uploadFile: gate.handler });
      await expect(page.getByText("Checking your file.")).toBeVisible();
      return gate.release;
    }),
    state("categories: upload refused", async (page) => {
      await toUploaded(page, { uploadFile: reply(422, PROBLEMS, { "Content-Type": "application/problem+json" }) });
      await expect(page.getByRole("heading", { name: "Your file was not accepted" })).toBeVisible();
    }),
    state("categories: upload too large", async (page) => {
      await toUploaded(page, { uploadFile: reply(413) });
      await expect(page.getByText("The file is too large.")).toBeVisible();
    }),
    state("categories: upload replaced", (page) => toReplaced(page)),
    state("categories: upload restored", async (page) => {
      await toReplaced(page);
      await page.getByRole("button", { name: "Restore previous version" }).click();
      await expect(page.getByText("The previous version is back.")).toBeVisible();
    }),
    ...sortAgainStates(),
    state("categories: upload list changed", async (page) => {
      await toUploaded(page, { confirmUpload: reply(409, { type: "about:blank", title: "Conflict", status: 409 }) });
      await page.getByRole("button", { name: "Replace my whole list (2 removed)" }).click();
      await expect(page.getByText("The list changed.")).toBeVisible();
    }),
  ];
}
