import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { expectNoAxeViolations } from "@/test/axe";
import { INVOICES, json } from "@/test/categories";
import { READY, item, wirePlan } from "@/test/plan";
import { renderReview } from "@/test/review";

afterEach(() => {
  vi.unstubAllGlobals();
});

function page(items: unknown[]): () => Response {
  return () => json({ items, page: 1, hasMore: false });
}

async function openFirstGroup(): Promise<void> {
  await userEvent.click(await screen.findByRole("button", { name: /^Other to Invoices/ }));
}

describe("Review moves: full names and the pair (AC-52, R2)", () => {
  it("given items with nested names and a pair, then each row shows old and new, topic and extra, and the confidence", async () => {
    wirePlan({
      items: page([
        item(1, {
          oldTopic: "Home/Energy",
          oldExtra: "Home/Energy/Bills",
          newTopic: "Finance/Invoices",
          newExtra: "Finance/Invoices/Acme",
          confidencePct: 62,
        }),
      ]),
    });
    await renderReview();
    await openFirstGroup();

    const row = (await screen.findByRole("checkbox")).closest("li");
    expect(row).not.toBeNull();
    const text = within(row as HTMLElement);
    expect(text.getByText("From topic Home/Energy, extra Home/Energy/Bills")).toBeInTheDocument();
    expect(text.getByText("To topic Finance/Invoices, extra Finance/Invoices/Acme")).toBeInTheDocument();
    expect(text.getByText("Model confidence 62 %")).toBeInTheDocument();
  });

  it("given a pair and a confidence, then the tick box is named by the mail alone and the pair is its description", async () => {
    wirePlan({
      items: page([
        item(1, { oldTopic: "Home/Energy", oldExtra: null, newTopic: "Finance/Invoices", newExtra: null, confidencePct: 62 }),
      ]),
    });
    await renderReview();
    await openFirstGroup();

    const box = await screen.findByRole("checkbox");
    expect(box).not.toHaveAccessibleName(/From topic|To topic|confidence/);
    expect(box).toHaveAccessibleDescription(/From topic Home\/Energy, extra none.*To topic Finance\/Invoices, extra none.*Model confidence 62 %/);
  });

  it("given a missing topic, extra or confidence, then the row says none and leaves the confidence out", async () => {
    wirePlan({ items: page([item(1, { oldTopic: null, oldExtra: null, newTopic: "Finance/Invoices", newExtra: null })]) });
    await renderReview();
    await openFirstGroup();

    expect(await screen.findByText("From topic none, extra none")).toBeInTheDocument();
    expect(screen.getByText("To topic Finance/Invoices, extra none")).toBeInTheDocument();
    expect(screen.queryByText(/Model confidence/)).not.toBeInTheDocument();
  });
});

describe("Review moves: the tip of a category (AC-52)", () => {
  it("given a category with a tip, then it is shown as plain text, labelled a suggestion, with a link to the edit view", async () => {
    wirePlan({ items: page([item(1, { tip: "Add billing@acme.example (4 mails) as a sender." }), item(2)]) });
    await renderReview();
    await openFirstGroup();

    expect(await screen.findByText("Add billing@acme.example (4 mails) as a sender.")).toBeInTheDocument();
    expect(screen.getByText(/suggestion, nothing was changed/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: `Open the edit view of ${INVOICES.name}` });
    expect(link).toHaveAttribute("href", `/categories?edit=${INVOICES.id}`);
    expect(screen.getAllByText("Add billing@acme.example (4 mails) as a sender.")).toHaveLength(1);
  });

  it("given a tip with markup, a URL and a markdown link, then it is text: no element, no link, no image", async () => {
    const hostile = '<a href="https://evil.example">click</a> <img src=x onerror=alert(1)> https://evil.example [here](https://evil.example)';
    wirePlan({ items: page([item(1, { tip: hostile })]) });
    const container = await renderReview();
    await openFirstGroup();

    expect(await screen.findByText(hostile)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector('a[href*="evil"]')).toBeNull();
    expect(screen.getAllByRole("link").every((link) => !(link.getAttribute("href") ?? "").includes("evil"))).toBe(true);
  });

  it("given a category without a tip, then no suggestion block shows", async () => {
    wirePlan({ items: page([item(1), item(2)]) });
    await renderReview();
    await openFirstGroup();
    await screen.findAllByRole("checkbox");

    expect(screen.queryByText(/suggestion, nothing was changed/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Open the edit view/ })).not.toBeInTheDocument();
  });
});

describe("Review moves: what moved on its own (R2)", () => {
  it("given moved, scheduled and skipped items, then one line says how many of each", async () => {
    wirePlan({ plan: () => json({ ...READY, auto: { moved: 5, scheduled: 12, skipped: 1 } }) });
    await renderReview();

    expect(await screen.findByText("5 mails were already moved on their own, 12 are scheduled and 1 was skipped.")).toBeInTheDocument();
  });

  it("given all three counts are 0, then the line is hidden", async () => {
    wirePlan();
    await renderReview();
    await screen.findByRole("heading", { name: "Mails that would move" });

    expect(screen.queryByText(/on their own/)).not.toBeInTheDocument();
  });
});

describe("Review moves: accessibility of the new content (AC-67)", () => {
  it("given the auto line, an open group, a pair and a tip, then axe finds no violations", async () => {
    wirePlan({
      plan: () => json({ ...READY, auto: { moved: 2, scheduled: 0, skipped: 0 } }),
      items: page([item(1, { oldTopic: "Home", newTopic: "Finance/Invoices", confidencePct: 40, tip: "A tip." })]),
    });
    const container = await renderReview();
    await openFirstGroup();
    await screen.findByText("A tip.");

    await expectNoAxeViolations(container);
  });
});
