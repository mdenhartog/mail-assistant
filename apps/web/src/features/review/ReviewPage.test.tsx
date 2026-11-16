import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { expectNoAxeViolations } from "@/test/axe";
import { INVOICES, NEWS, json } from "@/test/categories";
import { GONE_ID, NO_PLAN, OTHER_ID, PLAN_ID, READY, group as groupRow, itemsPage, wirePlan } from "@/test/plan";
import { renderReview } from "@/test/review";

afterEach(() => {
  vi.unstubAllGlobals();
});

const GROUP_BUTTON = /^Other to Invoices/;

describe("Review moves: groups (AC-12)", () => {
  it("given a plan with groups, then they are collapsed with a count and each has Approve group and Keep all in place", async () => {
    wirePlan();
    await renderReview();

    const toggle = await screen.findByRole("button", { name: GROUP_BUTTON });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(within(toggle).getByText("80 mails")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve group: Other to Invoices" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep all in place: Other to Invoices" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Newsletters to Invoices/ })).toBeInTheDocument();
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
    expect(document.title).toBe("Review moves - Mail Assistant");
  });

  it("given a category id that no longer resolves, then the group says so and nothing breaks", async () => {
    wirePlan({ plan: () => json({ ...READY, groups: [groupRow({ from: GONE_ID, count: 3 })] }) });
    await renderReview();

    expect(await screen.findByRole("button", { name: /^A category that no longer exists to Invoices/ })).toBeInTheDocument();
  });

  it("given a group is opened with Enter, then its mails load and the button reports it is expanded", async () => {
    wirePlan({ items: () => json(itemsPage(1, 3, false)) });
    await renderReview();

    const toggle = await screen.findByRole("button", { name: GROUP_BUTTON });
    toggle.focus();
    await userEvent.keyboard("{Enter}");

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findAllByRole("checkbox")).toHaveLength(3);
  });
});

describe("Review moves: group header (UX)", () => {
  const group = (name: RegExp): HTMLElement => {
    const item = screen.getByRole("button", { name }).closest("li");
    if (item === null) {
      throw new Error("group not found");
    }
    return item;
  };

  it("given nothing is decided, then the chip says so and Approve group is the secondary button", async () => {
    wirePlan();
    await renderReview();
    await screen.findByRole("button", { name: GROUP_BUTTON });

    const first = group(GROUP_BUTTON);
    expect(within(first).getByText("Not decided yet")).toBeInTheDocument();
    const approve = within(first).getByRole("button", { name: "Approve group: Other to Invoices" });
    expect(approve.className).toContain("bg-surface-raised");
    expect(approve.className).not.toContain("bg-primary");
  });

  it.each([
    [80, "All 80 will move"],
    [50, "50 of 80 will move"],
  ])("given %i of 80 approved, then the chip reads '%s'", async (approved, text) => {
    wirePlan({
      plan: () => json({ ...READY, groups: [groupRow({ approved })] }),
    });
    await renderReview();

    expect(await screen.findByText(text)).toBeInTheDocument();
  });

  it.each([
    [{ approved: 0, rejected: 80 }, "Stays in place"],
    [{ approved: 0, rejected: 30 }, "30 of 80 stay in place"],
    [{ approved: 50, rejected: 30 }, "50 of 80 will move, 30 stay in place"],
    [{ approved: 0, rejected: 0 }, "Not decided yet"],
  ])("given %o, then the chip reads '%s' (also after a reload)", async (counts, text) => {
    wirePlan({ plan: () => json({ ...READY, groups: [groupRow(counts)] }) });
    await renderReview();

    expect(await screen.findByText(text)).toBeInTheDocument();
  });

  it("given Keep all in place, then the plan is read again and the chip reads 'Stays in place'", async () => {
    let kept = false;
    wirePlan({
      plan: () => json({ ...READY, groups: [groupRow(kept ? { rejected: 80 } : {})] }),
      decisions: () => {
        kept = true;
        return json({ changed: 80 });
      },
    });
    await renderReview();

    await userEvent.click(await screen.findByRole("button", { name: "Keep all in place: Other to Invoices" }));

    expect(await within(group(GROUP_BUTTON)).findByText("Stays in place")).toBeInTheDocument();
  });

  it("given an example mail, then it shows under the title as plain text, outside the toggle button", async () => {
    wirePlan({
      plan: () =>
        json({
          ...READY,
          groups: [groupRow({ example: { senderName: "Acme <b>Billing</b>", senderAddress: "a@b.example", subject: "Your invoice" } })],
        }),
    });
    await renderReview();

    const line = await screen.findByText('For example: Acme <b>Billing</b>, "Your invoice"');
    expect(line.closest("button")).toBeNull();
    expect(line.querySelector("b")).toBeNull();
  });

  it("given 'Look at these mails first', then the group opens and the control goes away", async () => {
    wirePlan({ items: () => json(itemsPage(1, 3, false)) });
    await renderReview();
    await screen.findByRole("button", { name: GROUP_BUTTON });

    await userEvent.click(within(group(GROUP_BUTTON)).getByRole("button", { name: "Look at these mails first: Other to Invoices" }));

    expect(screen.getByRole("button", { name: GROUP_BUTTON })).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findAllByRole("checkbox")).toHaveLength(3);
    expect(screen.getByRole("button", { name: GROUP_BUTTON })).toHaveFocus();
  });
});

describe("Review moves: deciding (AC-13)", () => {
  it("given 'Select all 80 in this group', then it only selects and sends no decision", async () => {
    const seen = wirePlan({ items: () => json(itemsPage(1, 80, false)) });
    await renderReview();
    await userEvent.click(await screen.findByRole("button", { name: GROUP_BUTTON }));
    await screen.findAllByRole("checkbox");

    await userEvent.click(screen.getByRole("button", { name: "Select all 80 in this group" }));

    expect(screen.getAllByRole("checkbox").every((box) => (box as HTMLInputElement).checked)).toBe(true);
    expect(seen.filter((call) => call.method === "POST")).toEqual([]);
  });

  it("given Approve group, then the group decision is recorded with the counts the user saw", async () => {
    const seen = wirePlan();
    await renderReview();

    await userEvent.click(await screen.findByRole("button", { name: "Approve group: Other to Invoices" }));

    await waitFor(() => {
      expect(seen.find((call) => call.path === "/api/plan/decisions")?.body).toEqual({
        planId: PLAN_ID,
        itemCount: 82,
        scope: { group: { from: OTHER_ID, to: INVOICES.id }, groupCount: 80 },
        decision: "approved",
      });
    });
  });

  it("given Keep all in place, then the group is rejected", async () => {
    const seen = wirePlan();
    await renderReview();

    await userEvent.click(await screen.findByRole("button", { name: "Keep all in place: Other to Invoices" }));

    await waitFor(() => {
      expect(seen.find((call) => call.path === "/api/plan/decisions")?.body).toMatchObject({ decision: "rejected" });
    });
  });

  it("given three mails ticked, then Approve selected sends their ids and clears the selection", async () => {
    const seen = wirePlan({ items: () => json(itemsPage(1, 5, false)) });
    await renderReview();
    await userEvent.click(await screen.findByRole("button", { name: GROUP_BUTTON }));
    const boxes = await screen.findAllByRole("checkbox");
    for (const box of boxes.slice(0, 3)) {
      await userEvent.click(box);
    }

    await userEvent.click(screen.getByRole("button", { name: "Approve selected (3)" }));

    await waitFor(() => {
      expect(seen.find((call) => call.path === "/api/plan/decisions")?.body).toMatchObject({
        scope: { ids: [1, 2, 3] },
        decision: "approved",
      });
    });
    await waitFor(() => {
      expect(screen.getAllByRole("checkbox").some((box) => (box as HTMLInputElement).checked)).toBe(false);
    });
  });

  it("given the plan changed meanwhile (409), then a banner says so and offers a reload", async () => {
    wirePlan({ decisions: () => json({ type: "about:blank", title: "Conflict", status: 409 }, 409) });
    await renderReview();

    await userEvent.click(await screen.findByRole("button", { name: "Approve group: Other to Invoices" }));

    expect(await screen.findByText("The review changed.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload the review" })).toBeInTheDocument();
  });
});

describe("Review moves: approving (AC-13, AC-55)", () => {
  const APPROVED = {
    ...READY,
    groups: [
      groupRow({ count: 80, approved: 80 }),
      groupRow({ from: NEWS.id, count: 2, approved: 0 }),
    ],
    counts: { items: 82, pending: 2, approved: 80, rejected: 0 },
  };

  async function approvedPlan(): Promise<ReturnType<typeof wirePlan>> {
    let decided = false;
    const seen = wirePlan({
      plan: () => json(decided ? APPROVED : READY),
      decisions: () => {
        decided = true;
        return json({ changed: 80 });
      },
    });
    await renderReview();
    await userEvent.click(await screen.findByRole("button", { name: "Approve group: Other to Invoices" }));
    return seen;
  }

  it("given nothing is approved, then the bar button reads 0 and does nothing", async () => {
    wirePlan();
    await renderReview();

    const button = await screen.findByRole("button", { name: "Move 0 mails to their new categories" });
    expect(button).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(button);
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("given approved mails, then the button reads 'Move N mails to their new categories' and the summary names the counts per group", async () => {
    await approvedPlan();

    await userEvent.click(await screen.findByRole("button", { name: "Move 80 mails to their new categories" }));

    const dialog = await screen.findByRole("alertdialog", { name: "Move 80 mails?" });
    expect(within(dialog).getByText("Other to Invoices: 80 mails")).toBeInTheDocument();
    expect(within(dialog).getByText("Each mail gets its new category label in Gmail. Nothing is deleted and nothing is sent. You can move them back afterwards.")).toBeInTheDocument();
    const buttons = within(dialog).getAllByRole("button");
    expect(buttons.map((button) => button.textContent)).toEqual(["Not yet", "Move 80 mails to their new categories"]);
    expect(buttons[0]).toHaveFocus();
  });

  it("given an apply threshold and delay, then the summary names them", async () => {
    await approvedPlan();

    await userEvent.click(await screen.findByRole("button", { name: "Move 80 mails to their new categories" }));

    const dialog = await screen.findByRole("alertdialog", { name: "Move 80 mails?" });
    expect(
      within(dialog).getByText("More than 50 mails in 24 hours: the move starts after 30 minutes so you can still cancel in Telegram."),
    ).toBeInTheDocument();
  });

  it("given no apply settings, then the summary keeps the neutral sentence", async () => {
    wirePlan({
      plan: () => json({ ...READY, groups: [groupRow({ approved: 80 })], counts: { items: 82, pending: 2, approved: 80, rejected: 0 }, applyThreshold: null, applyDelayMinutes: null }),
    });
    await renderReview();

    await userEvent.click(await screen.findByRole("button", { name: "Move 80 mails to their new categories" }));

    const dialog = await screen.findByRole("alertdialog", { name: "Move 80 mails?" });
    expect(within(dialog).getByText(/When many mails move within a day, the move waits a while first/)).toBeInTheDocument();
  });

  it("given groups approved in different sessions, when the page is loaded again, then the summary shows the exact count per group (AC-13)", async () => {
    const later = {
      ...READY,
      groups: [
        groupRow({ count: 80, approved: 50 }),
        groupRow({ from: NEWS.id, count: 2, approved: 1 }),
      ],
      counts: { items: 82, pending: 31, approved: 51, rejected: 0 },
    };
    wirePlan({ plan: () => json(later) });
    await renderReview();

    await userEvent.click(await screen.findByRole("button", { name: "Move 51 mails to their new categories" }));

    const dialog = await screen.findByRole("alertdialog", { name: "Move 51 mails?" });
    expect(within(dialog).getByText("Other to Invoices: 50 mails")).toBeInTheDocument();
    expect(within(dialog).getByText("Newsletters to Invoices: 1 mail")).toBeInTheDocument();
  });

  it("given the summary is confirmed, then the plan and its count are approved and the scheduled state shows", async () => {
    const seen = await approvedPlan();
    await userEvent.click(await screen.findByRole("button", { name: "Move 80 mails to their new categories" }));
    await userEvent.click(await within(await screen.findByRole("alertdialog")).findByRole("button", { name: "Move 80 mails to their new categories" }));

    await waitFor(() => {
      expect(seen.find((call) => call.path === "/api/plan/approve")?.body).toEqual({ planId: PLAN_ID, itemCount: 82 });
    });
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("given Escape in the summary, then nothing is approved", async () => {
    const seen = await approvedPlan();
    await userEvent.click(await screen.findByRole("button", { name: "Move 80 mails to their new categories" }));
    await screen.findByRole("alertdialog");

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(seen.some((call) => call.path === "/api/plan/approve")).toBe(false);
  });

  it("given the approval fails, then a banner says nothing was changed", async () => {
    let decided = false;
    wirePlan({
      plan: () => json(decided ? APPROVED : READY),
      decisions: () => {
        decided = true;
        return json({ changed: 80 });
      },
      approve: () => json({}, 500),
    });
    await renderReview();
    await userEvent.click(await screen.findByRole("button", { name: "Approve group: Other to Invoices" }));
    await userEvent.click(await screen.findByRole("button", { name: "Move 80 mails to their new categories" }));
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Move 80 mails to their new categories" }));

    expect(await screen.findByText("Could not move your mails. Nothing was changed.")).toBeInTheDocument();
  });
});

describe("Review moves: building (AC-43)", () => {
  const PROGRESS = { checked: 340, cap: 5000, unclear: 0, estimate: 2000, notLookedAt: 0 };
  const BUILDING = { ...READY, state: "building", groups: [], progress: PROGRESS };

  it("given a plan being built, then it says how far it is of about how many and that nothing moves yet", async () => {
    wirePlan({ plan: () => json(BUILDING) });
    await renderReview();

    expect(await screen.findByText("340 of about 2000 checked, nothing moves yet.")).toBeInTheDocument();
    const bar = screen.getByRole("progressbar", { name: "Mails checked" });
    expect(bar).toHaveAttribute("aria-valuenow", "340");
    expect(bar).toHaveAttribute("aria-valuemax", "2000");
    expect(screen.queryByRole("button", { name: /Approve group/ })).not.toBeInTheDocument();
  });

  it("given the checked mails pass the estimate, then the text never names fewer mails in total than were checked", async () => {
    wirePlan({ plan: () => json({ ...BUILDING, progress: { ...PROGRESS, checked: 2100 } }) });
    await renderReview();

    expect(await screen.findByText("2100 of about 2100 checked, nothing moves yet.")).toBeInTheDocument();
  });

  it("given no estimate yet, then it says how many are checked so far, with no bar", async () => {
    wirePlan({ plan: () => json({ ...BUILDING, progress: { ...PROGRESS, estimate: null } }) });
    await renderReview();

    expect(await screen.findByText("340 checked so far, nothing moves yet.")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("given the build reached its cap, then the ready plan says how many older mails were not looked at", async () => {
    const progress = { checked: 5000, cap: 5000, unclear: 3, estimate: 7400, notLookedAt: 2400 };
    wirePlan({ plan: () => json({ ...READY, progress }) });
    await renderReview();

    expect(await screen.findByText("Older mail was not looked at.")).toBeInTheDocument();
    expect(screen.getByText(/2400 older mails were not looked at and stay where they are/)).toBeInTheDocument();
    expect(screen.getByText(/3 mails with two Assistant labels are left out/)).toBeInTheDocument();
  });

  it("given no mail was left out, then there is no not-looked-at banner", async () => {
    wirePlan();
    await renderReview();

    await screen.findByRole("button", { name: /^Other to Invoices/ });
    expect(screen.queryByText("Older mail was not looked at.")).not.toBeInTheDocument();
  });
});

describe("Review moves: the other states (AC-23)", () => {
  const LAST = { id: PLAN_ID, state: "applied", appliedAt: "2026-11-15T13:00:00Z", movedCount: 3 };
  const cases: [string, object, string][] = [
    ["no plan", NO_PLAN, "No review is open."],
    ["scheduled", { ...READY, state: "scheduled", applyAfter: "2026-11-15T14:20:00Z" }, "Your mails move at "],
    ["applying", { ...READY, state: "applying" }, "Your mails are being moved."],
    ["replaced", { ...READY, state: "replaced", groups: [] }, "This review was replaced."],
    ["cancelled", { ...READY, state: "cancelled", groups: [] }, "This review was cancelled."],
    ["discarded", { ...READY, state: "discarded", groups: [] }, "This review was too old."],
    ["applied", { ...READY, state: "applied", groups: [], lastPlan: LAST }, "3 mails were moved on 15 Nov at "],
    ["applied and already retired", { ...NO_PLAN, lastPlan: LAST }, "3 mails were moved on 15 Nov at "],
  ];

  it.each(cases)("given %s, then its banner shows", async (_name, plan, title) => {
    wirePlan({ plan: () => json(plan), items: () => json({ items: [], page: 1, hasMore: false }) });
    await renderReview();

    expect(await screen.findByText(new RegExp(`^${title}`))).toBeInTheDocument();
  });

  it("given no review is open, then it links to the categories", async () => {
    wirePlan({ plan: () => json(NO_PLAN) });
    await renderReview();

    expect(await screen.findByRole("link", { name: "Edit your categories" })).toHaveAttribute("href", "/categories");
  });

  it("given scheduled, then it says the move can be cancelled in Telegram", async () => {
    wirePlan({ plan: () => json({ ...READY, state: "scheduled", applyAfter: "2026-11-15T14:20:00Z" }) });
    await renderReview();

    expect(await screen.findByText(/Only labels change\. To stop this, use Cancel in the Telegram message\./)).toBeInTheDocument();
  });

  it.each([
    [1, "1 mail was moved on 15 Nov at "],
    [0, "0 mails were moved on 15 Nov at "],
  ])("given %i moved, then the banner counts them in the singular or plural", async (movedCount, title) => {
    wirePlan({
      plan: () => json({ ...NO_PLAN, lastPlan: { ...LAST, movedCount } }),
      items: () => json({ items: [], page: 1, hasMore: false }),
    });
    await renderReview();

    expect(await screen.findByText(new RegExp(`^${title}[0-9]{2}:[0-9]{2}[.]$`))).toBeInTheDocument();
  });

  it("given the moved time is unknown, then the banner still says how many moved", async () => {
    wirePlan({
      plan: () => json({ ...NO_PLAN, lastPlan: { ...LAST, appliedAt: null } }),
      items: () => json({ items: [], page: 1, hasMore: false }),
    });
    await renderReview();

    expect(await screen.findByText("3 mails were moved.")).toBeInTheDocument();
  });

  it("given an applied plan with skipped and failed mails, then each is listed with its reason", async () => {
    wirePlan({
      plan: () => json({ ...READY, state: "applied", groups: [], lastPlan: LAST }),
      items: () =>
        json({
          items: [
            { ...itemsFor(1), state: "applied", decision: "approved" },
            { ...itemsFor(2), state: "skipped", decision: "approved", reason: "You moved this mail yourself" },
            { ...itemsFor(3), state: "failed", decision: "approved", reason: null },
          ],
          page: 1,
          hasMore: false,
        }),
    });
    await renderReview();

    expect(await screen.findByText("1 skipped, 1 failed.")).toBeInTheDocument();
    expect(screen.getByText("You moved this mail yourself")).toBeInTheDocument();
    expect(screen.getByText("Gmail did not accept the change. It stays where it was.")).toBeInTheDocument();
    expect(screen.getByText(/Mails you changed yourself stay as you left them/)).toBeInTheDocument();
    expect(screen.getByText(/^3 mails were moved on 15 Nov at \d\d:\d\d\.$/)).toBeInTheDocument();
    expect(screen.getByText("Only labels changed; nothing was deleted.")).toBeInTheDocument();
    expect(screen.getByText("Subject 3")).toBeInTheDocument();
    expect(screen.queryByText("Subject 1")).not.toBeInTheDocument();
  });

  it("given a skipped mail without a reason, then it says the user moved it themselves", async () => {
    wirePlan({
      plan: () => json({ ...READY, state: "applied", groups: [], lastPlan: LAST }),
      items: () => json({ items: [{ ...itemsFor(2), state: "skipped", decision: "approved", reason: null }], page: 1, hasMore: false }),
    });
    await renderReview();

    expect(await screen.findByText("You moved this mail yourself, so I left it alone.")).toBeInTheDocument();
  });

  it("given Move back, then a red dialog asks first and confirming posts to the plan", async () => {
    const seen = wirePlan({ plan: () => json({ ...NO_PLAN, lastPlan: LAST }) });
    await renderReview();

    await userEvent.click(await screen.findByRole("button", { name: "Move back" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Move these mails back?" });
    expect(within(dialog).getAllByRole("button")[0]).toHaveFocus();
    await userEvent.click(within(dialog).getByRole("button", { name: "Move back" }));

    expect(await screen.findByText("Your mails are being moved back.")).toBeInTheDocument();
    expect(seen.some((call) => call.path === `/api/plan/${PLAN_ID}/move-back`)).toBe(true);
  });
});

describe("Review moves: loading and failing", () => {
  it("given the request is pending, then a skeleton with a busy status shows", async () => {
    wirePlan({ plan: () => new Promise<Response>(() => undefined) });
    await renderReview();

    expect(screen.getByRole("status")).toHaveTextContent("Loading your review");
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(document.querySelectorAll("[data-skeleton]").length).toBeGreaterThan(0);
  });

  it("given the load fails, then a friendly banner offers Try again", async () => {
    let calls = 0;
    wirePlan({ plan: () => (++calls === 1 ? json({}, 500) : json(READY)) });
    await renderReview();

    expect(await screen.findByText("Could not load your review.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("button", { name: GROUP_BUTTON })).toBeInTheDocument();
  });

  it("given the category list cannot be read, then the groups are not shown with wrong names", async () => {
    wirePlan({ categories: () => json({}, 500) });
    await renderReview();

    expect(await screen.findByText("Could not load your review.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Approve group/ })).not.toBeInTheDocument();
  });

  it("given a 429, then it says to wait", async () => {
    wirePlan({ plan: () => json({}, 429, { "Retry-After": "60" }) });
    await renderReview();

    expect(await screen.findByText("Too many requests.")).toBeInTheDocument();
  });

  it("has no axe violations on the ready plan", async () => {
    wirePlan();
    const container = await renderReview();
    await screen.findByRole("button", { name: GROUP_BUTTON });

    await expectNoAxeViolations(container);
  });
});

function itemsFor(id: number): Record<string, unknown> {
  return { id, senderName: `Sender ${String(id)}`, senderAddress: `s${String(id)}@example.com`, subject: `Subject ${String(id)}`, from: OTHER_ID, to: INVOICES.id, state: "pending", decision: "pending", reason: null };
}
