import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import {
  auditChannel,
  changeListElsewhere,
  INVOICES_ID,
  planCount,
  resetCategories,
  seedList,
  stackLogs,
  storedList,
  TRAVEL_ID,
  versions,
} from "./support/categoriesDb";
import { axeProblems, overflowProblem, settle, useDoubleText, VIEWPORTS } from "./support/checks";
import { lockWeb, resetState } from "./support/db";
import { signInThroughPage } from "./support/signin";

// The `categories` project (U-mail-categories-11, the R1 gate of INT-004): the Categories page through a real browser
// over the prod-like stack (edge, web, api, database over TLS). One worker, in file order, after every other project:
// the stack has one mailbox and one list. Owner SQL (support/categoriesDb.ts) puts the list back before each test; each
// test signs in for itself because the reset removes the sessions.
//
// What this project cannot show is everything the agent does with the stored list: the stack has no agent, no fake Gmail
// and no fake Telegram (the agent's Google and Telegram addresses are fixed in its code). The agent's half (new mail
// follows the list, the label rename by id, Undo, the notice) is tested against a real PostgreSQL with fake Gmail and
// Telegram in agents/mail-triage/tests; docs/release/mail-categories-r1.md lists which journey ran where.
test.describe.configure({ mode: "serial", timeout: 120_000 });

const INVOICES = "Invoices";
const TRAVEL = "Travel";
const SUMMARY_TITLE = /^Save \d+ changes?\?$/;

test.beforeEach(() => {
  resetState();
  resetCategories();
});

// The web image serves a page route only for `/`, `/login` and `/settings` (nginx.conf), so the page is reached the way a
// user does after signing in: through the navigation. A deep link to `/categories` is test 0 below.
async function openCategories(page: Page): Promise<void> {
  await page.getByRole("link", { name: "Categories" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Categories" })).toBeVisible();
}

async function openSeeded(page: Page): Promise<void> {
  seedList();
  await signInThroughPage(page);
  await openCategories(page);
  await expect(page.getByLabel("Name").first()).toBeVisible();
}

async function pressSave(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Save changes" }).click();
}

async function confirmSave(page: Page): Promise<void> {
  const dialog = page.getByRole("alertdialog", { name: SUMMARY_TITLE });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Save changes", exact: true }).click();
}

// 0 (AC-22, C-12)
test("a deep link to /categories and a reload serve the app", async ({ request }) => {
  expect((await request.get("/categories")).status()).toBe(200);
  expect((await request.get("/review")).status()).toBe(200);
});

// 1 (AC-22)
test("a visitor without a session is sent to the login page for /settings and the list api answers 401", async ({
  page,
  request,
}) => {
  await page.goto("/settings");
  await expect(page).toHaveURL(/\/login/);

  expect((await request.get("/api/categories")).status()).toBe(401);
  const put = await request.put("/api/categories", { data: { version: 0, categories: [] } });
  expect([401, 403]).toContain(put.status());
  expect(versions()).toEqual([]);
});

// 2 (AC-49)
test("before the agent has written version 1 the page says the categories are not ready", async ({ page }) => {
  await signInThroughPage(page);
  await openCategories(page);

  await expect(page.getByText("Your categories are still being set up.")).toBeVisible();
  await expect(page.getByLabel("Name")).toHaveCount(0);
  expect(versions()).toEqual([]);
});

// 3 (AC-1, C-12)
test("the page shows the list with name, description and number of mails, and Other", async ({ page }) => {
  await openSeeded(page);

  await expect(page.getByLabel("Name").nth(0)).toHaveValue(INVOICES);
  await expect(page.getByLabel("Description").nth(0)).toHaveValue("Invoices, receipts and payment confirmations");
  await expect(page.getByText("12 mails")).toBeVisible();
  await expect(page.getByLabel("Name").nth(1)).toHaveValue(TRAVEL);
  await expect(page.getByText("1 mail", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Other" })).toBeVisible();
  await expect(page.getByText("3 mails")).toBeVisible();
  await expect(page.getByText(/Mail already filed stays where it is\./).first()).toBeVisible();
  await expect(page.getByText("Your archive label is left alone.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Add to my list: Newsletters" })).toBeVisible();
});

// 4 (AC-2, AC-31 web half, AC-55)
test("edit and save: the summary says what happens, the list is stored whole as version 2 with an audit record", async ({
  page,
}) => {
  await openSeeded(page);

  await page.getByLabel("Description").nth(1).fill("Bookings, tickets, hotels and itineraries");
  await page.getByRole("button", { name: "Add category" }).click();
  await page.getByLabel("Name").last().fill("Bills");
  await page.getByLabel("Description").last().fill("Utility and phone bills");
  await pressSave(page);

  const dialog = page.getByRole("alertdialog", { name: SUMMARY_TITLE });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(`Change the description of "${TRAVEL}"`)).toBeVisible();
  await expect(dialog.getByText('Add "Bills"')).toBeVisible();
  expect(versions(), "nothing is stored before the user confirms").toEqual(["1|operator"]);

  await dialog.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await expect(page.getByText("Your list applies to new mail from now on.")).toBeVisible();

  expect(versions()).toEqual(["1|operator", "2|web"]);
  const stored = storedList(2);
  expect(stored.map((row) => row.name)).toEqual([INVOICES, TRAVEL, "Bills"]);
  expect(stored[1]?.description).toBe("Bookings, tickets, hotels and itineraries");
  expect(stored[0]?.id, "an unchanged category keeps its id").toBe(INVOICES_ID);
  expect(auditChannel(2), "the audit record names the web").toBe("web");
  expect(
    storedList(1).map((row) => row.name),
    "the earlier version is kept",
  ).toEqual([INVOICES, TRAVEL]);
  expect(planCount(), "R1 makes no review").toBe(0);

  await page.getByRole("link", { name: "Settings" }).click();
  await openCategories(page);
  await expect(page.getByLabel("Name")).toHaveCount(3);
});

// 5 (AC-2)
test("a save without a change makes no new version", async ({ page }) => {
  await openSeeded(page);

  const save = page.getByRole("button", { name: "Save changes" });
  await expect(save).toBeDisabled();
  await page.getByLabel("Name").nth(1).fill("Trips");
  await expect(save).toBeEnabled();
  await page.getByLabel("Name").nth(1).fill(TRAVEL);
  await expect(save).toBeDisabled();
  expect(versions()).toEqual(["1|operator"]);
});

// 6 (AC-2, AC-40 second half): one row per rule that the user can reach from the page
const RESERVED = "That name is kept for the assistant. Pick another.";
const REFUSED: { rule: string; name: string; description?: string; text: string }[] = [
  { rule: "empty name", name: "", text: "Give the category a name." },
  { rule: "slash", name: "Bills/Phone", text: "A name cannot contain a slash." },
  { rule: "reserved Other", name: "Other", text: RESERVED },
  { rule: "reserved Archive in other case", name: "ARCHIVE", text: RESERVED },
  { rule: "look-alike of Archive (fullwidth)", name: "Ａrchive", text: RESERVED },
  { rule: "duplicate in other case", name: "invoices", text: "Another category already has this name." },
  { rule: "name too long", name: "x".repeat(41), text: "Use at most 40 characters for the name." },
  { rule: "empty description", name: "Bills", description: "", text: "Say what belongs in this category." },
  {
    rule: "description too long",
    name: "Bills",
    description: "d".repeat(501),
    text: "Use at most 500 characters for the description.",
  },
];

for (const row of REFUSED) {
  test(`a refused value shows its reason in the field and stores nothing: ${row.rule}`, async ({ page }) => {
    await openSeeded(page);
    await page.getByRole("button", { name: "Add category" }).click();
    await page.getByLabel("Name").last().fill(row.name);
    await page.getByLabel("Description").last().fill(row.description ?? "Bills of any kind");
    await pressSave(page);
    const dialog = page.getByRole("alertdialog", { name: SUMMARY_TITLE });
    if (await dialog.isVisible()) {
      await dialog.getByRole("button", { name: "Save changes", exact: true }).click();
    }

    await expect(page.getByText(row.text)).toBeVisible();
    expect(versions()).toEqual(["1|operator"]);
  });
}

// 6b (AC-2, AC-40): the label of Travel still exists in Gmail until the agent renames it, so a new category may not take it
test("a new name that equals an existing Gmail label is refused and nothing is stored", async ({ page }) => {
  await openSeeded(page);

  await page.getByLabel("Name").nth(1).fill("Trips");
  await page.getByRole("button", { name: "Add category" }).click();
  await page.getByLabel("Name").last().fill(TRAVEL);
  await page.getByLabel("Description").last().fill("A second category with the name of the old label");
  await pressSave(page);
  const dialog = page.getByRole("alertdialog", { name: SUMMARY_TITLE });
  if (await dialog.isVisible()) {
    await dialog.getByRole("button", { name: "Save changes", exact: true }).click();
  }

  await expect(page.getByText("A Gmail label with this name already exists.")).toBeVisible();
  expect(versions()).toEqual(["1|operator"]);
});

// 7 (AC-3)
test("a list that changed elsewhere is refused with a conflict and the page shows the newest list", async ({ page }) => {
  await openSeeded(page);
  changeListElsewhere();

  await page.getByLabel("Description").nth(0).fill("Invoices and receipts");
  await pressSave(page);
  await confirmSave(page);

  await expect(page.getByText("The list changed somewhere else.")).toBeVisible();
  await expect(page.getByLabel("Name")).toHaveCount(3);
  await expect(page.getByLabel("Name").nth(2)).toHaveValue("Bills from elsewhere");
  expect(versions(), "the stale save stored nothing").toEqual(["1|operator", "2|operator"]);
  expect(storedList(2).map((row) => row.name)).toEqual([INVOICES, TRAVEL, "Bills from elsewhere"]);
});

// 8 (AC-40 web half, C-15)
test("a rename keeps the category id, makes no review and the summary says only the label name changes", async ({ page }) => {
  await openSeeded(page);

  await page.getByLabel("Name").nth(1).fill("Trips");
  await pressSave(page);
  const dialog = page.getByRole("alertdialog", { name: SUMMARY_TITLE });
  await expect(dialog.getByText(`Rename "${TRAVEL}" to "Trips"`)).toBeVisible();
  await expect(dialog.getByText("Renaming only changes the label name.")).toBeVisible();
  await dialog.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  const [invoices, trips] = storedList(2);
  expect(invoices?.id).toBe(INVOICES_ID);
  expect(trips).toMatchObject({ id: TRAVEL_ID, name: "Trips", description: "Bookings, tickets and itineraries" });
  expect(planCount(), "a rename makes no plan").toBe(0);
});

// 9 (AC-53)
test("an older category is added to the list with its own button", async ({ page }) => {
  await openSeeded(page);

  await page.getByRole("button", { name: "Add to my list: Newsletters" }).click();
  await expect(page.getByLabel("Name").last()).toHaveValue("Newsletters");
  await page.getByLabel("Description").last().fill("Newsletters and mailing lists");
  await pressSave(page);
  await confirmSave(page);
  await expect(page.getByText("Saved.")).toBeVisible();

  expect(storedList(2).map((row) => row.name)).toEqual([INVOICES, TRAVEL, "Newsletters"]);
});

// 10 (C-12)
test("a removed category can be put back before saving, and is gone from the next version once saved", async ({ page }) => {
  await openSeeded(page);

  await page.getByRole("button", { name: `Delete ${TRAVEL}` }).click();
  await expect(page.getByText(`Removed ${TRAVEL}.`)).toBeVisible();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByLabel("Name").nth(1)).toHaveValue(TRAVEL);

  await page.getByRole("button", { name: `Delete ${TRAVEL}` }).click();
  await pressSave(page);
  await expect(page.getByRole("alertdialog", { name: SUMMARY_TITLE }).getByText(/^Remove "/)).toBeVisible();
  await confirmSave(page);
  await expect(page.getByText("Saved.")).toBeVisible();

  expect(storedList(2).map((row) => row.name)).toEqual([INVOICES]);
  expect(storedList(1)).toHaveLength(2);
});

// 11 (AC-23, keyboard)
test("the whole save flow works with the keyboard alone", async ({ page }) => {
  await openSeeded(page);

  await page.getByLabel("Description").nth(1).focus();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type("Bookings and tickets");
  await page.getByRole("button", { name: "Save changes" }).focus();
  await page.keyboard.press("Enter");

  const dialog = page.getByRole("alertdialog", { name: SUMMARY_TITLE });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Keep editing" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Save changes", exact: true })).toBeFocused();
  await page.keyboard.press("Enter");

  await expect(page.getByText("Saved.")).toBeVisible();
  expect(storedList(2)[1]?.description).toBe("Bookings and tickets");
});

// 12 (AC-32 list part)
test("a locked web refuses the list calls and the page falls back to sign-in; nothing is stored", async ({ page }) => {
  await openSeeded(page);
  await page.getByLabel("Description").nth(0).fill("Changed after the lock");
  lockWeb();

  expect((await page.request.get("/api/categories")).status()).toBe(401);
  await pressSave(page);
  await confirmSave(page);

  await expect(page).toHaveURL(/\/login/);
  expect(versions()).toEqual(["1|operator"]);
});

// 13 (AC-23): the states the real stack can reach, at the four viewports of the spec and at 200 % text
const STATES = ["loaded", "validation error", "save summary", "saved", "conflict"] as const;

async function reach(page: Page, state: (typeof STATES)[number]): Promise<void> {
  await expect(page.getByLabel("Name").first()).toBeVisible();
  if (state === "loaded") {
    return;
  }
  if (state === "validation error") {
    await page.getByRole("button", { name: "Add category" }).click();
    await pressSave(page);
    await expect(page.getByText("Give the category a name.")).toBeVisible();
    return;
  }
  if (state === "conflict") {
    changeListElsewhere();
  }
  await page.getByLabel("Description").nth(0).fill("Invoices and receipts");
  await pressSave(page);
  if (state === "save summary") {
    await expect(page.getByRole("alertdialog", { name: SUMMARY_TITLE })).toBeVisible();
    return;
  }
  await confirmSave(page);
  await expect(page.getByText(state === "saved" ? "Saved." : "The list changed somewhere else.")).toBeVisible();
}

for (const viewport of VIEWPORTS) {
  test(`${String(viewport.width)} px: every reachable state has no overflow and no axe violation`, async ({ page }) => {
    await page.setViewportSize(viewport);
    for (const state of STATES) {
      resetCategories();
      await page.context().clearCookies();
      await openSeeded(page);
      await reach(page, state);
      await settle(page);
      expect.soft(await overflowProblem(page), `${state}: horizontal scroll`).toBeNull();
      expect.soft(await axeProblems(page), `${state}: axe`).toEqual([]);
    }
    resetCategories();
    await page.context().clearCookies();
    await signInThroughPage(page);
    await openCategories(page);
    await expect(page.getByText("Your categories are still being set up.")).toBeVisible();
    await settle(page);
    expect.soft(await axeProblems(page), "not ready: axe").toEqual([]);
  });

  test(`${String(viewport.width)} px at 200 % text: no overflow and no axe violation`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await useDoubleText(page);
    await openSeeded(page);
    await settle(page);
    expect.soft(await overflowProblem(page), "loaded: horizontal scroll").toBeNull();
    expect.soft(await axeProblems(page), "loaded: axe").toEqual([]);
    await page.getByLabel("Description").nth(0).fill("Invoices and receipts");
    await pressSave(page);
    await expect(page.getByRole("alertdialog", { name: SUMMARY_TITLE })).toBeVisible();
    await settle(page);
    expect.soft(await overflowProblem(page), "summary: horizontal scroll").toBeNull();
    expect.soft(await axeProblems(page), "summary: axe").toEqual([]);
  });
}

// 14 (AC-30): last, so the logs hold everything the tests above did. Canaries stand for what must never be logged: the
// text of a refused name and description (they may carry what the user typed) and of a saved description.
test("canary strings typed into names and descriptions are in no log of the stack", async ({ page }) => {
  const canary = `canary-${String(Date.now())}-${Math.random().toString(36).slice(2, 10)}`;
  await openSeeded(page);

  await page.getByRole("button", { name: "Add category" }).click();
  await page.getByLabel("Name").last().fill(`${canary}/refused`);
  await page.getByLabel("Description").last().fill(`${canary} refused description`);
  await pressSave(page);
  await expect(page.getByText("A name cannot contain a slash.")).toBeVisible();

  await page.getByLabel("Name").last().fill(`${canary}-ok`);
  await page.getByLabel("Description").last().fill(`${canary} saved description`);
  await pressSave(page);
  await confirmSave(page);
  await expect(page.getByText("Saved.")).toBeVisible();
  expect(storedList(2).map((row) => row.name)).toContain(`${canary}-ok`);

  const logs = stackLogs();
  expect(logs, "the logs hold the requests, so the absence of the canary means something").toContain("/api/categories");
  expect(logs.includes(canary), "a canary string is in a log of the stack").toBe(false);
});
