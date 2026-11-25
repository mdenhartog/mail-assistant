import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { auditChannel, seedList, versions } from "./support/categoriesDb";
import { axeProblems, overflowProblem, SCHEMES, settle, useDoubleText, VIEWPORTS } from "./support/checks";
import { resetState } from "./support/db";
import { goldenFile, uploadToPreview } from "./support/labelStructure";
import {
  applyAutoPlan,
  autoApplyMinutes,
  autoItemStates,
  autoPlanState,
  AUTO_ITEMS,
  cancelAutoPlan,
  INVOICES_TIP,
  latestRequestId,
  REVIEW_ITEMS,
  requestRows,
  resetResort,
  reviewItemStates,
  reviewPlanThreshold,
  seedAutoPlan,
  seedBothPlans,
  seedReviewPlan,
} from "./support/resort";
import { signInThroughPage } from "./support/signin";

// The `label-structure-r2` project (U-label-structure-27, the R2 gate of INT-008): "Sort everything again" with a
// threshold, the two plans it makes, the tips and the archive label name, through a real browser over the prod-like
// stack (edge, web, api, database over TLS). One worker, in file order, after `label-structure`: the stack has one
// mailbox and one list, and the specs reset them by owner SQL.
//
// What this project cannot show: the prod-like stack has no agent, no Gmail and no Telegram. Building the two plans,
// approving the sure items, moving mail after the delay, Cancel in Telegram, and the rename of the Gmail archive label are
// the agent's half. Here owner SQL (support/resort.ts) writes what the agent would have written, in the shape the
// migrations allow, and the browser journey checks what the user sees and what the api stores. The agent's half is
// covered by the agent's own tests with a fake Gmail and Telegram; docs/release lists which step ran where.
//
// Rate limit: a sort-again request counts against the hourly limit of list saves (default 10). Every test resets the
// request table, and the whole project makes at most one request per test.
test.describe.configure({ mode: "serial", timeout: 180_000 });

const THRESHOLD = 80;
const SORT_BUTTON = "Sort everything again";
const GROUP_INVOICES = /^Other to Invoices/;
const GROUP_TRAVEL = /^Other to Travel/;
const ARCHIVE = "Archief";

test.beforeEach(() => {
  resetState();
  resetResort();
});

async function openCategories(page: Page): Promise<void> {
  await page.getByRole("link", { name: "Categories" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Categories" })).toBeVisible();
  await expect(page.locator("button[data-edit]").first()).toBeVisible();
}

async function openSeeded(page: Page): Promise<void> {
  seedList();
  await signInThroughPage(page);
  await openCategories(page);
}

async function reloadCategories(page: Page): Promise<void> {
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Categories" })).toBeVisible();
  await expect(page.locator("button[data-edit]").first()).toBeVisible();
}

async function openReview(page: Page): Promise<void> {
  await page.getByRole("link", { name: /^Review moves/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Review moves" })).toBeVisible();
}

const thresholdField = (page: Page): ReturnType<Page["getByLabel"]> => page.getByLabel("Confidence threshold (%)");
const sortButton = (page: Page): ReturnType<Page["getByRole"]> => page.getByRole("button", { name: SORT_BUTTON });

/** Types the threshold and presses the button; the request is accepted when the status line appears. */
async function sendRequest(page: Page, threshold: number): Promise<void> {
  await thresholdField(page).fill(String(threshold));
  await sortButton(page).click();
  await expect(page.getByText("Your request is in.")).toBeVisible();
}

async function expectNoViolations(page: Page, label: string): Promise<void> {
  for (const scheme of SCHEMES) {
    await page.emulateMedia({ colorScheme: scheme });
    await settle(page);
    expect.soft(await axeProblems(page), `${label}, ${scheme}: axe`).toEqual([]);
    expect.soft(await overflowProblem(page), `${label}, ${scheme}: horizontal scroll`).toBeNull();
  }
}

// 1 (AC-45, AC-46): the request, the button disabled with its reason, the plans and what the page says before the delay
test("the threshold is sent once, the button says why it is off, and the page shows the numbers while nothing has moved", async ({
  page,
}) => {
  await openSeeded(page);

  await expect(page.getByRole("heading", { level: 2, name: SORT_BUTTON })).toBeVisible();
  await expect(thresholdField(page)).toHaveValue("50");
  await expect(page.getByText("Nothing moves until a short delay; you can cancel in Telegram.")).toBeVisible();
  await expect(page.getByText("The model's confidence is its own estimate, not a calibrated probability.")).toBeVisible();

  // The sentence under the field follows the typed number.
  await thresholdField(page).fill(String(THRESHOLD));
  await expect(page.getByText(`the model is at least ${String(THRESHOLD)} % sure of moves by itself`)).toBeVisible();

  await sortButton(page).click();
  await expect(page.getByText("Your request is in. The assistant is preparing the plan and Telegram tells you what will move.")).toBeVisible();
  await expect(sortButton(page)).toBeDisabled();
  await expect(sortButton(page)).toHaveAccessibleDescription(/Your request is in/);
  expect(requestRows(), "one request, from the web, with the typed threshold").toEqual([`${String(THRESHOLD)}|web`]);

  // The agent answers with two plans of the request. The page that reloads says a plan is open and links to it.
  seedAutoPlan(latestRequestId());
  seedReviewPlan(latestRequestId());
  await reloadCategories(page);
  await expect(page.getByText(/A plan is open\. Wait until it has been applied or cancelled\./)).toBeVisible();
  await expect(sortButton(page)).toBeDisabled();
  await expect(sortButton(page)).toHaveAccessibleDescription(/A plan is open/);
  expect(requestRows(), "the reload sent nothing").toHaveLength(1);

  await page.getByRole("link", { name: "Follow it in Review moves" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Review moves" })).toBeVisible();
  await expect(page.getByText(`${String(AUTO_ITEMS)} mails are scheduled.`)).toBeVisible();
  await expect(page.getByRole("button", { name: GROUP_INVOICES })).toBeVisible();
  await expect(page.getByRole("button", { name: GROUP_TRAVEL })).toBeVisible();

  // Nothing moved before the delay: the plan waits, no mail is applied, no review mail is decided.
  expect(autoPlanState()).toBe("scheduled");
  expect(autoApplyMinutes(), "the apply waits about the configured delay").toBeGreaterThan(15);
  expect(autoItemStates()).toEqual([`approved|${String(AUTO_ITEMS)}`]);
  expect(reviewItemStates()).toEqual([`pending/pending|${String(REVIEW_ITEMS)}`]);
  expect(reviewPlanThreshold(), "the review plan copied the threshold of the request").toBe(THRESHOLD);
});

// 1 (edge): a threshold outside 50 to 100 is refused before any request is sent
test("a threshold the api would refuse is stopped in the field and no request is made", async ({ page }) => {
  await openSeeded(page);

  await thresholdField(page).fill("49");
  await sortButton(page).click();
  await expect(page.getByText("Use a whole number from 50 to 100.")).toBeVisible();
  await expect(thresholdField(page)).toBeFocused();
  await expect(thresholdField(page)).toHaveAttribute("aria-invalid", "true");
  expect(requestRows()).toEqual([]);

  await thresholdField(page).fill("100");
  await expect(page.getByText("Use a whole number from 50 to 100.")).toHaveCount(0);
  await sendRequest(page, 100);
  expect(requestRows()).toEqual(["100|web"]);
});

// 2 (AC-47, AC-48, AC-52): after the apply, the sure items are moved, the rest wait in Review moves with their tips
test("after the apply the page counts what moved on its own and the review plan holds the rest with its tip", async ({ page }) => {
  await openSeeded(page);
  seedBothPlans(THRESHOLD);
  await openReview(page);
  await expect(page.getByText(`${String(AUTO_ITEMS)} mails are scheduled.`)).toBeVisible();

  // The agent applies the auto plan: four mails move, one is skipped because the user moved it first.
  applyAutoPlan();
  expect(autoPlanState()).toBe("applied");
  expect(autoItemStates()).toEqual([`applied|${String(AUTO_ITEMS - 1)}`, "skipped|1"]);
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Review moves" })).toBeVisible();
  await expect(page.getByText("4 mails were already moved on their own and 1 was skipped.")).toBeVisible();

  // The rest is in Review moves: two groups; the tip belongs to the category of the first group and is a suggestion.
  await expect(page.getByRole("button", { name: GROUP_INVOICES })).toBeVisible();
  await expect(page.getByRole("button", { name: GROUP_TRAVEL })).toBeVisible();
  await page.getByRole("button", { name: GROUP_INVOICES }).click();
  const tip = page.getByRole("complementary", { name: "Tip for Invoices" });
  await expect(tip).toBeVisible();
  await expect(tip.getByText("This is a suggestion, nothing was changed.")).toBeVisible();
  await expect(tip.getByText(INVOICES_TIP)).toBeVisible();
  await expect(tip.getByRole("link", { name: "Open the edit view of Invoices" })).toHaveAttribute("href", /\/categories\?edit=/);
  await expect(page.getByRole("checkbox")).toHaveCount(4);
  await expect(page.getByText("Model confidence 45 %")).toBeVisible();
  await expect(page.getByText("To topic Invoices, extra none").first()).toBeVisible();

  await page.getByRole("button", { name: GROUP_TRAVEL }).click();
  await expect(page.getByRole("checkbox")).toHaveCount(6);
  await expect(page.getByRole("complementary", { name: "Tip for Travel" })).toHaveCount(0);

  // Reading the page decided nothing.
  expect(reviewItemStates()).toEqual([`pending/pending|${String(REVIEW_ITEMS)}`]);

  // The tip leads to the edit view of the category.
  await tip.getByRole("link", { name: "Open the edit view of Invoices" }).click();
  await expect(page.getByRole("region", { name: /^Edit category$/ })).toBeVisible();
});

// 3 (AC-50): Cancel. The web app has no Cancel button (the one way is the Telegram message, which the page says), so the
// Telegram answer is written by SQL as the agent would and the page is checked for what it then tells.
test("a Cancel while the auto plan waits leaves every mail where it was and the page no longer counts it", async ({ page }) => {
  await openSeeded(page);
  seedBothPlans(THRESHOLD);
  await openReview(page);
  await expect(page.getByText(`${String(AUTO_ITEMS)} mails are scheduled.`)).toBeVisible();

  cancelAutoPlan();
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Review moves" })).toBeVisible();
  await expect(page.getByRole("button", { name: GROUP_INVOICES })).toBeVisible();
  await expect(page.getByText(/mails? (is|are) scheduled/)).toHaveCount(0);
  await expect(page.getByText(/moved on (its|their) own/)).toHaveCount(0);

  expect(autoPlanState()).toBe("cancelled");
  expect(autoItemStates(), "nothing was moved").toEqual([`approved|${String(AUTO_ITEMS)}`]);
  expect(reviewItemStates()).toEqual([`pending/pending|${String(REVIEW_ITEMS)}`]);

  // With the auto plan ended and the review plan still open, the Categories page still says a plan is open.
  await page.getByRole("link", { name: "Categories" }).click();
  await expect(page.getByText(/A plan is open\./)).toBeVisible();
  await expect(sortButton(page)).toBeDisabled();
});

// 4 (AC-41 to AC-43, web half): the archive label is part of the list: refused names say why, a saved name stays
test("the archive label is saved with the list, is there after a reload and is in the export and the next preview", async ({
  page,
}) => {
  await openSeeded(page);
  const field = page.getByLabel("Archive label");
  await expect(field).toBeVisible();
  await expect(page.getByText("Mail in this label is never sorted or moved. Renaming it renames the Gmail label, nothing else.")).toBeVisible();

  async function saveChanges(): Promise<void> {
    await page.getByRole("button", { name: "Save changes" }).click();
    const dialog = page.getByRole("alertdialog", { name: /^Save \d+ changes?\?$/ });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Change the archive label")).toBeVisible();
    await dialog.getByRole("button", { name: "Save changes", exact: true }).click();
  }

  // A Gmail system label is refused with the reason, and nothing is stored.
  await field.fill("INBOX");
  await saveChanges();
  await expect(page.getByText("This is a Gmail label of its own and cannot be used here.")).toBeVisible();
  await expect(field).toHaveAttribute("aria-invalid", "true");
  expect(versions(), "the refused name stored no new version").toEqual(["1|operator"]);

  await field.fill(ARCHIVE);
  await saveChanges();
  await expect(page.getByText("Saved.")).toBeVisible();
  expect(versions()).toHaveLength(2);
  expect(auditChannel(2)).toBe("web");

  await reloadCategories(page);
  await expect(page.getByLabel("Archive label")).toHaveValue(ARCHIVE);

  // The export carries the stored name.
  const exported = await page.request.get("/api/categories/export");
  expect(exported.status()).toBe(200);
  expect(await exported.text()).toMatch(new RegExp(`archiveLabel:\\s*["']?${ARCHIVE}["']?\\s*$`, "m"));

  // The golden file names Assistant/Archive, so its preview sees the archive label as a change against the stored one.
  const answered = page.waitForResponse((response) => response.url().includes("/api/categories/upload") && response.request().method() === "POST");
  await uploadToPreview(page, goldenFile());
  const preview = (await (await answered).json()) as { archiveLabelChanged: boolean };
  expect(preview.archiveLabelChanged).toBe(true);
});

// 5 (a11y): the Categories page with the new section and Review moves with tips, at the four widths, light and dark
for (const viewport of VIEWPORTS) {
  test(`${String(viewport.width)} px: the Categories page with the sort-again section has no axe violation, light and dark`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await openSeeded(page);
    await expect(page.getByRole("heading", { level: 2, name: SORT_BUTTON })).toBeVisible();
    await expectNoViolations(page, "section idle");

    await thresholdField(page).fill("49");
    await sortButton(page).click();
    await expect(page.getByText("Use a whole number from 50 to 100.")).toBeVisible();
    await expectNoViolations(page, "section with a field error");

    await sendRequest(page, THRESHOLD);
    await expectNoViolations(page, "request sent, button off");

    seedAutoPlan(latestRequestId());
    seedReviewPlan(latestRequestId());
    await reloadCategories(page);
    await expect(page.getByText(/A plan is open\./)).toBeVisible();
    await expectNoViolations(page, "plan open, button off");
  });

  test(`${String(viewport.width)} px: Review moves with the counts and the tips has no axe violation, light and dark`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await openSeeded(page);
    seedBothPlans(THRESHOLD);
    await openReview(page);
    await expect(page.getByText(`${String(AUTO_ITEMS)} mails are scheduled.`)).toBeVisible();
    await expectNoViolations(page, "ready, auto plan scheduled");

    applyAutoPlan();
    await page.reload();
    await expect(page.getByText("4 mails were already moved on their own and 1 was skipped.")).toBeVisible();
    await page.getByRole("button", { name: GROUP_INVOICES }).click();
    await expect(page.getByRole("complementary", { name: "Tip for Invoices" })).toBeVisible();
    await expectNoViolations(page, "group open with its tip");
  });

  test(`${String(viewport.width)} px at 200 % text: both pages do not scroll sideways and have no axe violation`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await useDoubleText(page);
    await openSeeded(page);
    await settle(page);
    expect.soft(await overflowProblem(page), "categories: horizontal scroll").toBeNull();
    expect.soft(await axeProblems(page), "categories: axe").toEqual([]);

    seedBothPlans(THRESHOLD);
    await openReview(page);
    await page.getByRole("button", { name: GROUP_INVOICES }).click();
    await expect(page.getByRole("complementary", { name: "Tip for Invoices" })).toBeVisible();
    await settle(page);
    expect.soft(await overflowProblem(page), "review: horizontal scroll").toBeNull();
    expect.soft(await axeProblems(page), "review: axe").toEqual([]);
  });
}
