import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { axeProblems, overflowProblem, SCHEMES, settle, VIEWPORTS } from "./support/checks";
import { resetState, seedSettings } from "./support/db";
import {
  agentDeletesIfDue,
  agentFinishesRename,
  emptyTimers,
  itemStates,
  MERGED,
  migrationState,
  PLAN,
  PLAN_LABELS,
  PLAN_MAILS,
  RENAMED,
  restoreRequests,
  seedDeletedLabel,
  seedEmptyLabel,
  seedRenamePlan,
  SKIPPED,
  storedConfirmation,
  storedWaitMinutes,
} from "./support/labelRename";
import { seedList } from "./support/categoriesDb";
import { resetReview } from "./support/reviewDb";
import { signInThroughPage } from "./support/signin";

// The `label-prefix-removal` project (U-label-prefix-removal-14, the gate of INT-010): the one-time rename of the old
// `Assistant/...` labels (preview, skip, typed confirmation, merge, result, restore), the recently deleted list and the
// label cleanup settings, through a real browser over the prod-like stack (edge, web, api, database over TLS). One worker,
// in file order, after `label-structure-r2`: the stack has one mailbox, one list and one settings row, and the specs reset
// them by owner SQL.
//
// What this project cannot show: the prod-like stack has no agent, no Gmail and no Telegram. Building the plan, renaming
// and merging in Gmail, the empty-label timers and the delete are the agent's half. Owner SQL (support/labelRename.ts)
// writes what the agent would have written, in the shape revision 0030 allows, and the browser journey checks what the
// user sees and what the api stores (the confirmation and the restore request). The agent's half is covered by the agent's
// own tests with a fake Gmail.
test.describe.configure({ mode: "serial", timeout: 180_000 });

const THREE_VIEWPORTS = VIEWPORTS.filter((viewport) => [375, 768, 1280].includes(viewport.width));
const RENAME_SECTION = "Rename your labels";
const DELETED_SECTION = "Recently deleted labels";
const CLEANUP_TILE = "Label cleanup";
const POLL_WAIT_MS = 20_000; // the page reads the plan every 5 seconds while it is confirmed

test.beforeEach(() => {
  resetState();
  resetReview();
});

async function openCategories(page: Page): Promise<void> {
  await page.getByRole("link", { name: "Categories" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Categories" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Edit / }).first()).toBeVisible();
}

async function reloadCategories(page: Page): Promise<void> {
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Categories" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Edit / }).first()).toBeVisible();
}

/** Seeds the pending plan, signs in and opens the Categories page with the rename preview on it. */
async function openPreview(page: Page): Promise<string> {
  const hash = seedRenamePlan();
  await signInThroughPage(page);
  await openCategories(page);
  await expect(page.getByRole("heading", { level: 2, name: RENAME_SECTION })).toBeVisible();
  await expect(page.getByText(`${String(PLAN_LABELS)} labels, ${String(PLAN_MAILS)} mails`)).toBeVisible();
  return hash;
}

const renameSection = (page: Page): ReturnType<Page["getByRole"]> => page.getByRole("region", { name: RENAME_SECTION });
const deletedSection = (page: Page): ReturnType<Page["getByRole"]> => page.getByRole("region", { name: DELETED_SECTION });
const startButton = (page: Page): ReturnType<Page["getByRole"]> => page.getByRole("button", { name: "Rename these labels" });
const dialog = (page: Page): ReturnType<Page["getByRole"]> => page.getByRole("alertdialog");
const skipBox = (page: Page, oldName: string): ReturnType<Page["getByRole"]> => page.getByRole("checkbox", { name: `Skip ${oldName}` });

/** Opens the typed confirmation for the labels that are not skipped. */
async function openConfirmation(page: Page, count: number): Promise<void> {
  await startButton(page).click();
  await expect(page.getByRole("alertdialog", { name: `Rename ${String(count)} labels?` })).toBeVisible();
}

async function confirmWithTypedWord(page: Page): Promise<void> {
  await dialog(page).getByRole("textbox").fill("RENAME");
  await dialog(page).getByRole("button", { name: "Rename labels" }).click();
}

async function expectNoViolations(page: Page, label: string): Promise<void> {
  for (const scheme of SCHEMES) {
    await page.emulateMedia({ colorScheme: scheme });
    await settle(page);
    expect.soft(await axeProblems(page), `${label}, ${scheme}: axe`).toEqual([]);
    expect.soft(await overflowProblem(page), `${label}, ${scheme}: horizontal scroll`).toBeNull();
  }
}

// 1 (AC 4, AC 5): the preview shows the plan and changes nothing, a label can be skipped, the typed word confirms, the api
// stores the confirmation, and the page shows the result when the agent is done
test("the preview shows the plan and changes nothing, the typed word confirms it with the skipped label, and the result follows", async ({
  page,
}) => {
  const hash = await openPreview(page);

  // The preview: most mails first, each card says what the label is now and becomes; nothing is stored yet.
  const cards = renameSection(page).getByRole("listitem");
  await expect(cards).toHaveCount(PLAN_LABELS);
  await expect(cards.first()).toContainText(MERGED.oldName);
  await expect(cards.last()).toContainText(SKIPPED.oldName);
  await expect(renameSection(page).getByRole("group", { name: RENAMED.oldName })).toContainText("Becomes");
  await expect(renameSection(page).getByRole("group", { name: RENAMED.oldName })).toContainText(RENAMED.newName);
  expect(migrationState(), "reading the preview changes nothing").toBe("pending");
  expect(storedConfirmation()).toBeNull();

  // The user keeps one label as it is; the count follows.
  await skipBox(page, SKIPPED.oldName).check();
  await expect(page.getByText(`${String(PLAN_LABELS - 1)} labels will be renamed.`)).toBeVisible();
  await expect(renameSection(page).getByText("Skipped: keeps its name.")).toBeVisible();

  // A wrong word stops in the dialog and sends nothing.
  await openConfirmation(page, PLAN_LABELS - 1);
  await dialog(page).getByRole("textbox").fill("7");
  await dialog(page).getByRole("button", { name: "Rename labels" }).click();
  await expect(dialog(page).getByRole("alert")).toContainText("That does not match.");
  expect(storedConfirmation(), "a wrong word stored nothing").toBeNull();

  await confirmWithTypedWord(page);
  await expect(page.getByRole("status", { name: "Renaming is in progress" })).toBeVisible();

  // What the api stored: the confirmation of this plan with the skipped id, from the web; the plan is confirmed and the
  // api did not touch an item (renaming is the agent's).
  expect(migrationState()).toBe("confirmed");
  expect(storedConfirmation()).toEqual({ planHash: hash, skippedIds: [SKIPPED.id], channel: "web" });
  expect(itemStates()).toEqual([...PLAN].map((item) => `${item.id}|planned`).sort());

  // The agent renames and merges, then marks the plan done; the page reads it again by itself and shows the result.
  agentFinishesRename();
  const result = page.getByRole("region", { name: "Renaming finished" });
  await expect(result).toBeVisible({ timeout: POLL_WAIT_MS });
  await expect(result.getByText(`${String(PLAN_LABELS - 1)} of ${String(PLAN_LABELS)} labels renamed, 1 skipped`)).toBeVisible();
  await expect(result.getByText("Gmail apps may show the old names for a while.")).toBeVisible();
  await expect(result.getByText(`${RENAMED.oldName} is now ${RENAMED.newName}`)).toBeVisible();
  await expect(result.getByText(`${SKIPPED.oldName} was skipped and keeps its name`)).toBeVisible();
  await expect(startButton(page)).toHaveCount(0);
  await expect(result.getByRole("button", { name: "Restore the old names" })).toBeEnabled();
  expect(migrationState()).toBe("done");
});

// 2 (AC 20): a merge into an existing label is announced in the preview and reported in the result
test("a merge is announced before the rename and reported as merged afterwards", async ({ page }) => {
  await openPreview(page);

  const merge = renameSection(page).getByRole("group", { name: MERGED.oldName });
  await expect(merge).toContainText(`${String(MERGED.mailCount)} mails`);
  await expect(merge).toContainText(`Merge ${String(MERGED.mailCount)} mails into an existing label`);
  await expect(renameSection(page).getByRole("group", { name: RENAMED.oldName })).not.toContainText("Merge");

  await openConfirmation(page, PLAN_LABELS);
  await confirmWithTypedWord(page);
  await expect(page.getByRole("status", { name: "Renaming is in progress" })).toBeVisible();
  expect(storedConfirmation()?.skippedIds, "nothing was skipped").toEqual([]);

  agentFinishesRename();
  expect(itemStates()).toEqual([...PLAN].map((item) => `${item.id}|done`).sort());
  await reloadCategories(page);
  const result = page.getByRole("region", { name: "Renaming finished" });
  await expect(result).toBeVisible();
  await expect(result.getByText(`${MERGED.oldName} was merged into ${MERGED.newName}`)).toBeVisible();
  await expect(result.getByText(`${String(PLAN_LABELS)} of ${String(PLAN_LABELS)} labels renamed`)).toBeVisible();
});

// 1 (AC 5): the restore of the old names is a request the agent processes; the page asks once
test("the restore asks first, stores one request from the web and then says the old names are coming back", async ({ page }) => {
  await openPreview(page);
  await openConfirmation(page, PLAN_LABELS);
  await confirmWithTypedWord(page);
  await expect(page.getByRole("status", { name: "Renaming is in progress" })).toBeVisible();
  agentFinishesRename();
  await reloadCategories(page);
  const result = page.getByRole("region", { name: "Renaming finished" });
  await expect(result).toBeVisible();
  expect(restoreRequests()).toEqual([]);

  // Keeping the new names stores nothing.
  await result.getByRole("button", { name: "Restore the old names" }).click();
  await expect(page.getByRole("alertdialog", { name: "Restore the old names?" })).toBeVisible();
  await dialog(page).getByRole("button", { name: "Keep the new names" }).click();
  await expect(dialog(page)).toHaveCount(0);
  expect(restoreRequests()).toEqual([]);

  await result.getByRole("button", { name: "Restore the old names" }).click();
  await dialog(page).getByRole("button", { name: "Restore names" }).click();
  await expect(page.getByRole("status").filter({ hasText: "The old names are being restored." })).toBeVisible();
  await expect(result.getByRole("button", { name: "Restore the old names" })).toBeDisabled();
  expect(restoreRequests(), "one request, from the web, not yet processed").toEqual(["web|open"]);
});

// 3 (AC 7, AC 29): an empty label is deleted only after its own waiting time, and the record is listed
test("an empty label past its wait is deleted by the agent cycle and listed under recently deleted", async ({ page }) => {
  seedList();
  seedEmptyLabel("Label_Due", 10, 5); // empty for 10 minutes, waits 5: due
  seedEmptyLabel("Label_Waiting", 10, 720); // empty for 10 minutes, waits 12 hours: not due
  seedDeletedLabel("Label_Ancient", "Reizen/Ancient", 40); // older than the retention of 30 days
  await signInThroughPage(page);
  await openCategories(page);

  await expect(deletedSection(page).getByText("No label was deleted in the last 30 days.")).toBeVisible();

  expect(agentDeletesIfDue("Label_Waiting", "Reizen/Waiting"), "a label within its wait is kept").toBe(0);
  expect(agentDeletesIfDue("Label_Due", "Reizen/<b>Oud</b>"), "a label past its wait is deleted").toBe(1);
  expect(emptyTimers(), "the timer of the deleted label is gone, the other keeps running").toBe(1);

  await reloadCategories(page);
  const entries = deletedSection(page).getByRole("listitem");
  await expect(entries).toHaveCount(1);
  // The name is text, never markup.
  await expect(entries.first()).toContainText("Reizen/<b>Oud</b>");
  await expect(entries.first().locator("time")).toHaveAttribute("datetime", /^\d{4}-\d{2}-\d{2}T/);
  await expect(deletedSection(page).getByText(/listed here for 30 days/)).toBeVisible();
  await expect(deletedSection(page).getByText("Reizen/Ancient")).toHaveCount(0);
  await expect(deletedSection(page).getByText("Reizen/Waiting")).toHaveCount(0);
  // There is no plan to rename any more, so the page shows no rename section.
  await expect(page.getByRole("heading", { level: 2, name: RENAME_SECTION })).toHaveCount(0);
});

// 3 (AC 33 web half): the waiting time is typed as hours and minutes and stored in minutes; a value out of range stops at the field
test("the waiting time of 2 hours 30 minutes is stored as 150 minutes and a value out of range shows the message", async ({ page }) => {
  seedSettings();
  await signInThroughPage(page);
  const tile = page.getByRole("region", { name: CLEANUP_TILE });
  const hours = tile.getByLabel("Hours", { exact: true });
  const minutes = tile.getByLabel("Minutes", { exact: true });
  await expect(hours).toHaveValue("12");
  await expect(minutes).toHaveValue("0");
  expect(storedWaitMinutes(), "the stored default").toBe(720);

  await hours.fill("2");
  await minutes.fill("30");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status").filter({ hasText: /Saved at \d{2}:\d{2}\./ })).toBeVisible();
  expect(storedWaitMinutes()).toBe(150);

  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
  await expect(tile.getByLabel("Hours", { exact: true })).toHaveValue("2");
  await expect(tile.getByLabel("Minutes", { exact: true })).toHaveValue("30");

  // 13 hours is above the range: the inline message names the range, focus goes to the field and nothing is sent.
  await tile.getByLabel("Hours", { exact: true }).fill("13");
  await tile.getByLabel("Minutes", { exact: true }).fill("0");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "The waiting time can be 5 minutes to 12 hours. The default is 12 hours." })).toBeVisible();
  await expect(tile.getByLabel("Hours", { exact: true })).toHaveAttribute("aria-invalid", "true");
  expect(storedWaitMinutes(), "the refused value stored nothing").toBe(150);
});

// 4 (AC 17): the whole journey at three viewports, light and dark: the preview, the dialog, the result, the restore dialog,
// the recently deleted list and the settings tile with its message
for (const viewport of THREE_VIEWPORTS) {
  test(`${String(viewport.width)} px: the rename journey and the cleanup settings have no axe violation, light and dark`, async ({ page }) => {
    await page.setViewportSize(viewport);
    seedDeletedLabel("Label_Gone", "Reizen/Oud", 2);
    await openPreview(page);
    await expect(deletedSection(page).getByRole("listitem")).toHaveCount(1);
    await expectNoViolations(page, "preview");

    await skipBox(page, SKIPPED.oldName).check();
    await expectNoViolations(page, "preview with a skipped label");

    await openConfirmation(page, PLAN_LABELS - 1);
    await expectNoViolations(page, "confirmation dialog");

    await confirmWithTypedWord(page);
    await expect(page.getByRole("status", { name: "Renaming is in progress" })).toBeVisible();
    await expectNoViolations(page, "in progress");

    agentFinishesRename();
    await reloadCategories(page);
    await expect(page.getByRole("region", { name: "Renaming finished" })).toBeVisible();
    await expectNoViolations(page, "result");

    await page.getByRole("button", { name: "Restore the old names" }).click();
    await expect(page.getByRole("alertdialog", { name: "Restore the old names?" })).toBeVisible();
    await expectNoViolations(page, "restore dialog");
    await dialog(page).getByRole("button", { name: "Restore names" }).click();
    await expect(page.getByRole("status").filter({ hasText: "The old names are being restored." })).toBeVisible();
    await expectNoViolations(page, "restore requested");
  });

  test(`${String(viewport.width)} px: the label cleanup tile has no axe violation with and without a message, light and dark`, async ({ page }) => {
    await page.setViewportSize(viewport);
    seedSettings();
    await signInThroughPage(page);
    const tile = page.getByRole("region", { name: CLEANUP_TILE });
    await expect(tile).toBeVisible();
    await expectNoViolations(page, "settings");

    await tile.getByLabel("Hours", { exact: true }).fill("13");
    await tile.getByLabel("Minutes", { exact: true }).fill("0");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "The waiting time can be" })).toBeVisible();
    await expectNoViolations(page, "settings with a message");
  });
}
