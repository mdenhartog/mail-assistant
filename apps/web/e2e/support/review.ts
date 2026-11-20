import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";

import { held, PLAN, planItems, reply, stubApi } from "./stubs";
import type { Handler, Handlers } from "./stubs";
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

const GROUP = /^Other to Invoices/;
const APPROVED = {
  ...PLAN,
  groups: PLAN.groups.map((group, index) => (index === 0 ? { ...group, approved: 20 } : group)),
  counts: { items: 33, pending: 13, approved: 20, rejected: 0 },
};
const LAST = { id: PLAN.id, state: "applied", endedAt: "2026-11-15T13:00:00Z", movedCount: 3 };
const NO_PLAN = { ...PLAN, id: null, state: null, groups: [], counts: { items: 0, pending: 0, approved: 0, rejected: 0 } };

async function toReady(page: Page, handlers: Handlers = {}): Promise<void> {
  await stubApi(page, { signedIn: true, ...handlers });
  await page.goto("/review");
  await expect(page.getByRole("button", { name: GROUP })).toBeVisible();
}

async function toOpen(page: Page, handlers: Handlers = {}): Promise<void> {
  await toReady(page, handlers);
  await page.getByRole("button", { name: GROUP }).click();
  await expect(page.getByRole("checkbox").first()).toBeVisible();
}

/** The plan answers `PLAN` until a decision was recorded, then the same plan with 20 approved mails. */
function decidedAfterApproval(): Handlers {
  let decided = false;
  const answer: Handler = async (route, call) => {
    await reply(200, decided ? APPROVED : PLAN)(route, call);
  };
  const decision: Handler = async (route, call) => {
    decided = true;
    await reply(200, { changed: 20 })(route, call);
  };
  return { getPlan: answer, postDecision: decision };
}

async function toSummary(page: Page, handlers: Handlers = {}): Promise<void> {
  await toReady(page, { ...decidedAfterApproval(), ...handlers });
  await page.getByRole("button", { name: "Approve group: Other to Invoices" }).click();
  await page.getByRole("button", { name: "Move 20 mails to their new categories" }).first().click();
  await expect(page.getByRole("alertdialog", { name: "Move 20 mails?" })).toBeVisible();
}

async function toApplied(page: Page, handlers: Handlers = {}): Promise<void> {
  await stubApi(page, {
    signedIn: true,
    getPlan: reply(200, { ...PLAN, state: "applied", groups: [], lastPlan: LAST }),
    getPlanItems: reply(200, {
      page: 1,
      hasMore: false,
      items: [
        { ...(planItems(1, 1, false) as { items: object[] }).items[0], id: 1, state: "skipped", decision: "approved", reason: "You moved this mail yourself" },
        { ...(planItems(2, 1, false) as { items: object[] }).items[0], id: 2, state: "failed", decision: "approved", reason: null },
      ],
    }),
    ...handlers,
  });
  await page.goto("/review");
  await expect(page.getByText(/^3 mails were moved on /)).toBeVisible();
}

function banner(name: string, plan: unknown, text: string): UiState {
  return state(name, async (page) => {
    await stubApi(page, { signedIn: true, getPlan: reply(200, plan) });
    await page.goto("/review");
    await expect(page.getByText(text)).toBeVisible();
  });
}

/** The states of the Review moves page (AC-23); the same checks run on them as on the other pages. */
export function reviewStates(): UiState[] {
  return [
    state("review: loading", async (page) => {
      const gate = held(reply(200, PLAN));
      await stubApi(page, { signedIn: true, getPlan: gate.handler });
      await page.goto("/review");
      await expect(page.getByText("Loading your review")).toBeVisible();
      return gate.release;
    }),
    banner("review: no review", NO_PLAN, "No review is open."),
    state("review: building", async (page) => {
      await stubApi(page, { signedIn: true, getPlan: reply(200, { ...PLAN, state: "building", groups: [], progress: { checked: 340, cap: 5000, unclear: 0, estimate: 2000, notLookedAt: 0 } }) });
      await page.goto("/review");
      await expect(page.getByText("340 of about 2000 checked, nothing moves yet.")).toBeVisible();
    }),
    state("review: building, no estimate", async (page) => {
      await stubApi(page, { signedIn: true, getPlan: reply(200, { ...PLAN, state: "building", groups: [], progress: { checked: 340, cap: 5000, unclear: 0, estimate: null, notLookedAt: 0 } }) });
      await page.goto("/review");
      await expect(page.getByText("340 checked so far, nothing moves yet.")).toBeVisible();
    }),
    state("review: badge on another page", async (page) => {
      await stubApi(page, { signedIn: true });
      await page.goto("/settings");
      await expect(page.getByRole("link", { name: "Review moves 33 open items" })).toBeVisible();
    }),
    state("review: ready", (page) => toReady(page)),
    state("review: cap reached", (page) => toReady(page, { getPlan: reply(200, { ...PLAN, progress: { checked: 5000, cap: 5000, unclear: 2, estimate: 7400, notLookedAt: 2400 } }) })),
    state("review: group open", (page) => toOpen(page)),
    state("review: mails ticked", async (page) => {
      await toOpen(page);
      await page.getByRole("button", { name: "Select all 20 in this group" }).click();
      await expect(page.getByText("20 of 20 selected")).toBeVisible();
    }),
    state("review: summary", (page) => toSummary(page)),
    state("review: approving", async (page) => {
      const gate = held(reply(200, { state: "scheduled", applyAfter: "2026-11-15T14:20:00Z" }));
      await toSummary(page, { postApprove: gate.handler });
      await page.getByRole("alertdialog").getByRole("button", { name: "Move 20 mails to their new categories" }).click();
      return gate.release;
    }),
    banner("review: scheduled", { ...PLAN, state: "scheduled", groups: [], applyAfter: "2026-11-15T14:20:00Z" }, "Only labels change. To stop this, use Cancel in the Telegram message."),
    banner("review: applying", { ...PLAN, state: "applying", groups: [] }, "Your mails are being moved."),
    state("review: applied", (page) => toApplied(page)),
    state("review: move back asked", async (page) => {
      await toApplied(page);
      await page.getByRole("button", { name: "Move back" }).click();
      await expect(page.getByRole("alertdialog", { name: "Move these mails back?" })).toBeVisible();
    }),
    state("review: moving back", async (page) => {
      await toApplied(page);
      await page.getByRole("button", { name: "Move back" }).click();
      await page.getByRole("alertdialog").getByRole("button", { name: "Move back" }).click();
      await expect(page.getByText("Your mails are being moved back.")).toBeVisible();
    }),
    banner("review: replaced", { ...PLAN, state: "replaced", groups: [] }, "This review was replaced."),
    banner("review: cancelled", { ...PLAN, state: "cancelled", groups: [] }, "This review was cancelled."),
    banner("review: discarded", { ...PLAN, state: "discarded", groups: [] }, "This review was too old."),
    state("review: load failed", async (page) => {
      await stubApi(page, { signedIn: true, getPlan: reply(500) });
      await page.goto("/review");
      await expect(page.getByText("Could not load your review.")).toBeVisible();
    }),
    state("review: too many requests", async (page) => {
      await stubApi(page, { signedIn: true, getPlan: reply(429, undefined, { "Retry-After": "60" }) });
      await page.goto("/review");
      await expect(page.getByText("Too many requests.")).toBeVisible();
    }),
    state("review: group failed to load", async (page) => {
      await toReady(page, { getPlanItems: reply(500) });
      await page.getByRole("button", { name: GROUP }).click();
      await expect(page.getByText("Could not load these mails.")).toBeVisible();
    }),
    state("review: plan changed", async (page) => {
      await toReady(page, { postDecision: reply(409, { type: "about:blank", title: "Conflict", status: 409 }) });
      await page.getByRole("button", { name: "Approve group: Other to Invoices" }).click();
      await expect(page.getByText("The review changed.")).toBeVisible();
    }),
    state("review: locked (403)", async (page) => {
      await toReady(page, { postDecision: reply(403) });
      await page.getByRole("button", { name: "Approve group: Other to Invoices" }).click();
      await expect(page.getByRole("heading", { name: "Access refused" })).toBeVisible();
    }),
  ];
}
