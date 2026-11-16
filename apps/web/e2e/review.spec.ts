import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { stackLogs } from "./support/categoriesDb";
import { axeProblems, overflowProblem, settle, useDoubleText, VIEWPORTS } from "./support/checks";
import { lockWeb, resetState } from "./support/db";
import {
  applyDelayMinutes,
  cancelFromTelegram,
  itemStates,
  markApplied,
  openMoveBackRequests,
  planState,
  resetReview,
  seedPlan,
} from "./support/reviewDb";
import type { PlanSeed } from "./support/reviewDb";
import { signInThroughPage } from "./support/signin";

// The `review` project (U-mail-categories-19, the R2 gate of INT-004): the page "Review moves" through a real browser over
// the prod-like stack (edge, web, api, database over TLS). One worker, in file order, after `categories`: the stack has
// one mailbox. Owner SQL (support/reviewDb.ts) puts the plan the agent would have built; each test signs in for itself.
//
// What this project cannot show: the stack has no agent, no fake Gmail and no fake Telegram. Building the plan from a
// changed list, moving the mail in Gmail, Move back in Gmail and the Cancel button in Telegram are the agent's half. Here
// SQL stands in for the agent's writes (plan state, item state) and the browser journey checks what the user sees and what
// the api stores. The agent's half is tested by its pytest with fakes; docs/release/mail-categories-r2.md lists which step
// ran where.
test.describe.configure({ mode: "serial", timeout: 120_000 });

const GROUP = /^Other to Invoices/;
const CANARY = `canary-${String(Date.now())}-${Math.random().toString(36).slice(2, 10)}`;
const BELOW_THRESHOLD: PlanSeed = { items: 20, threshold: 100, delayMinutes: 20, canary: CANARY };
const ABOVE_THRESHOLD: PlanSeed = { items: 20, threshold: 10, delayMinutes: 20, canary: CANARY };
const SCHEDULED_TEXT = "Only labels change. You can cancel in Telegram until then.";

test.beforeEach(() => {
  resetState();
  resetReview();
});

async function openReview(page: Page): Promise<void> {
  await signInThroughPage(page);
  await page.getByRole("link", { name: /^Review moves/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Review moves" })).toBeVisible();
}

async function openReady(page: Page, seed: PlanSeed): Promise<void> {
  seedPlan(seed);
  await openReview(page);
  await expect(page.getByRole("button", { name: GROUP })).toBeVisible();
}

async function openSummary(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Approve group: Other to Invoices" }).click();
  await page.getByRole("button", { name: "Move 20 mails, labels only" }).first().click();
  await expect(page.getByRole("alertdialog", { name: "Move 20 mails?" })).toBeVisible();
}

async function approveGroup(page: Page): Promise<void> {
  await openSummary(page);
  await page.getByRole("alertdialog").getByRole("button", { name: "Move 20 mails, labels only" }).click();
  await expect(page.getByText(SCHEDULED_TEXT)).toBeVisible();
}

// 1 (AC-9, AC-13)
test("approving the group of a ready plan stores the decisions and schedules the plan; the page moves nothing", async ({ page }) => {
  await openReady(page, BELOW_THRESHOLD);
  expect(itemStates()).toEqual(["pending/pending|20"]);

  await approveGroup(page);

  expect(planState()).toBe("scheduled");
  expect(itemStates()).toEqual(["approved/approved|20"]);
  expect(applyDelayMinutes(), "under the threshold the agent may start at once").toBeLessThan(1);
});

// 2 (AC-14, AC-41)
test("once the plan is applied the page says so and Move back asks the agent exactly once", async ({ page }) => {
  await openReady(page, BELOW_THRESHOLD);
  await approveGroup(page);
  markApplied();
  await page.reload();
  await expect(page.getByText(/mails? (were|was) moved on /)).toBeVisible();

  await page.getByRole("button", { name: "Move back" }).click();
  const dialog = page.getByRole("alertdialog", { name: "Move these mails back?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Move back" }).click();

  await expect(page.getByText("Your mails are being moved back.")).toBeVisible();
  expect(openMoveBackRequests()).toBe(1);
  expect(planState(), "the page never changes the plan itself").toBe("applied");
});

// 3 (AC-42)
test("an approval above the threshold waits and a Cancel from Telegram stops it", async ({ page }) => {
  await openReady(page, ABOVE_THRESHOLD);

  await approveGroup(page);

  expect(planState()).toBe("scheduled");
  const wait = applyDelayMinutes();
  expect(wait, "the move waits about the configured delay").toBeGreaterThan(18);
  expect(wait).toBeLessThanOrEqual(20);

  cancelFromTelegram();
  await page.reload();
  await expect(page.getByText("This review was cancelled.")).toBeVisible();
  expect(planState()).toBe("cancelled");
  expect(itemStates(), "the plan was cancelled before any item moved").toEqual(["approved/approved|20"]);
});

// 4 (AC-32): a lock is a 401 and the sign-in page; it says nothing about the lock
test("a locked web refuses the plan calls with 401 and the page falls back to sign-in", async ({ page }) => {
  await openReady(page, BELOW_THRESHOLD);
  lockWeb();

  expect((await page.request.get("/api/plan")).status()).toBe(401);
  await page.getByRole("button", { name: "Approve group: Other to Invoices" }).click();
  await expect(page).toHaveURL(/\/login/);
  expect(planState()).toBe("ready");
  expect(itemStates()).toEqual(["pending/pending|20"]);
});

// 5 (AC-23): the states the real stack can reach, at the four viewports and at 200 % text
const STATES = ["no review", "ready", "group open", "summary", "scheduled", "cancelled", "applied"] as const;

async function reach(page: Page, state: (typeof STATES)[number]): Promise<void> {
  if (state === "no review") {
    await openReview(page);
    await expect(page.getByText("No review is open.")).toBeVisible();
    return;
  }
  await openReady(page, ABOVE_THRESHOLD);
  if (state === "ready") {
    return;
  }
  if (state === "group open") {
    await page.getByRole("button", { name: GROUP }).click();
    await expect(page.getByRole("checkbox").first()).toBeVisible();
    return;
  }
  if (state === "summary") {
    await openSummary(page);
    return;
  }
  await approveGroup(page);
  if (state === "scheduled") {
    return;
  }
  if (state === "cancelled") {
    cancelFromTelegram();
  } else {
    markApplied();
  }
  await page.reload();
  await expect(page.getByText(state === "cancelled" ? "This review was cancelled." : /mails? (were|was) moved on /)).toBeVisible();
}

for (const viewport of VIEWPORTS) {
  test(`${String(viewport.width)} px: every reachable state has no overflow and no axe violation`, async ({ page }) => {
    await page.setViewportSize(viewport);
    for (const state of STATES) {
      resetState();
      resetReview();
      await page.context().clearCookies();
      await reach(page, state);
      await settle(page);
      expect.soft(await overflowProblem(page), `${state}: horizontal scroll`).toBeNull();
      expect.soft(await axeProblems(page), `${state}: axe`).toEqual([]);
    }
  });

  test(`${String(viewport.width)} px at 200 % text: no overflow and no axe violation`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await useDoubleText(page);
    await openReady(page, ABOVE_THRESHOLD);
    await settle(page);
    expect.soft(await overflowProblem(page), "ready: horizontal scroll").toBeNull();
    expect.soft(await axeProblems(page), "ready: axe").toEqual([]);
    await page.getByRole("button", { name: GROUP }).click();
    await expect(page.getByRole("checkbox").first()).toBeVisible();
    await settle(page);
    expect.soft(await overflowProblem(page), "group open: horizontal scroll").toBeNull();
    expect.soft(await axeProblems(page), "group open: axe").toEqual([]);
  });
}

// 6 (AC-30): last, so the logs hold everything the tests above did. The canary stands for a sender and a subject.
test("canary strings in the sender and subject of the planned mails are in no log of the stack", async ({ page }) => {
  await openReady(page, ABOVE_THRESHOLD);
  await page.getByRole("button", { name: GROUP }).click();
  await expect(page.getByText(`${CANARY} subject 1`).first()).toBeVisible();
  await page.getByRole("button", { name: "Approve group: Other to Invoices" }).click();
  await page.getByRole("button", { name: "Move 20 mails, labels only" }).first().click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Move 20 mails, labels only" }).click();
  await expect(page.getByText(SCHEDULED_TEXT)).toBeVisible();

  const logs = stackLogs();
  expect(logs, "the logs hold the requests, so the absence of the canary means something").toContain("/api/plan");
  expect(logs.includes(CANARY), "a canary string is in a log of the stack").toBe(false);
});
