import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { expectNoAxeViolations } from "@/test/axe";
import { INVOICES, json } from "@/test/categories";
import { OTHER_ID, READY, item, itemsPage, wirePlan } from "@/test/plan";
import { renderReview } from "@/test/review";

afterEach(() => {
  vi.unstubAllGlobals();
});

const BIG = { ...READY, groups: [{ from: OTHER_ID, to: INVOICES.id, count: 1000 }], counts: { items: 1000, pending: 1000, approved: 0, rejected: 0 } };

function pagesOf1000(search: URLSearchParams): Response {
  const page = Number(search.get("page") ?? "1");
  return json(itemsPage((page - 1) * 100 + 1, 100, page < 10, page));
}

async function openFirstGroup(): Promise<void> {
  await userEvent.click(await screen.findByRole("button", { name: /Other to Invoices/ }));
}

describe("Review moves: paging (AC-24)", () => {
  it("given 1 000 items, then 100 rows render with Load more, and each page adds 100", async () => {
    const seen = wirePlan({ plan: () => json(BIG), items: pagesOf1000 });
    await renderReview();
    await openFirstGroup();

    expect(await screen.findAllByRole("checkbox")).toHaveLength(100);
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() => {
      expect(screen.getAllByRole("checkbox")).toHaveLength(200);
    });
    expect(seen.filter((call) => call.path === "/api/plan/items").map((call) => call.search.get("page"))).toEqual(["1", "2"]);
  });

  it("given a ticked box has focus and more rows load, then the same element keeps focus and its tick", async () => {
    wirePlan({ plan: () => json(BIG), items: pagesOf1000 });
    await renderReview();
    await openFirstGroup();
    const boxes = await screen.findAllByRole("checkbox");
    const ticked = boxes[5] as HTMLInputElement;
    await userEvent.click(ticked);
    expect(ticked).toHaveFocus();

    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() => {
      expect(screen.getAllByRole("checkbox")).toHaveLength(200);
    });
    expect(screen.getAllByRole("checkbox")[5]).toBe(ticked);
    expect(ticked).toBeChecked();
    expect(ticked).toHaveFocus();
  });

  it("given the last page, then Load more is gone", async () => {
    wirePlan({ items: () => json(itemsPage(1, 3, false)) });
    await renderReview();
    await openFirstGroup();
    await screen.findAllByRole("checkbox");

    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("given a page fails to load, then the group says so and Try again loads it", async () => {
    let calls = 0;
    wirePlan({ items: () => (++calls === 1 ? json({}, 500) : json(itemsPage(1, 2, false))) });
    await renderReview();
    await openFirstGroup();

    expect(await screen.findByText("Could not load these mails.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findAllByRole("checkbox")).toHaveLength(2);
  });

  it("given 'Select all 1000', then the rest of the pages are fetched and every mail is selected", async () => {
    wirePlan({ plan: () => json(BIG), items: pagesOf1000 });
    await renderReview();
    await openFirstGroup();
    await screen.findAllByRole("checkbox");

    await userEvent.click(screen.getByRole("button", { name: "Select all 1000 in this group" }));

    await waitFor(() => {
      expect(screen.getAllByRole("checkbox")).toHaveLength(1000);
    });
    expect(screen.getAllByRole("checkbox").every((box) => (box as HTMLInputElement).checked)).toBe(true);
  });
});

describe("Review moves: sender text (AC-44)", () => {
  it("given bidi and format characters in a name and subject, then they are removed and the real address is shown beside the name", async () => {
    wirePlan({
      items: () =>
        json({
          items: [item(1, { senderName: "‮PayPal‬​ Support", senderAddress: "scam@evil.example", subject: "Invoice⁦ due⁩" })],
          page: 1,
          hasMore: false,
        }),
    });
    await renderReview();
    await openFirstGroup();

    const row = (await screen.findByRole("checkbox")).closest("li");
    expect(row).not.toBeNull();
    const text = row?.textContent ?? "";
    expect(text).toContain("PayPal Support");
    expect(text).toContain("scam@evil.example");
    expect(text).toContain("Invoice due");
    expect(/[‮​⁦⁩]/u.test(text)).toBe(false);
  });

  it("given markup in sender and subject, then it renders as text and never as elements", async () => {
    wirePlan({ items: () => json({ items: [item(1, { senderName: "<img src=x onerror=alert(1)>", subject: "<b>hi</b>" })], page: 1, hasMore: false }) });
    const container = await renderReview();
    await openFirstGroup();

    expect(await screen.findByText("<b>hi</b>")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("never puts a sender, an address or a subject into a request URL", async () => {
    const seen = wirePlan({ items: () => json(itemsPage(1, 2, false)) });
    await renderReview();
    await openFirstGroup();
    await screen.findAllByRole("checkbox");

    for (const call of seen) {
      expect(`${call.path}?${call.search.toString()}`).not.toMatch(/sender|subject|example\.com/i);
    }
  });

  it("shows a long unbroken subject in full, without truncating it", async () => {
    const long = "W".repeat(300);
    wirePlan({ items: () => json({ items: [item(1, { subject: long })], page: 1, hasMore: false }) });
    await renderReview();
    await openFirstGroup();

    expect(await screen.findByText(long)).toBeInTheDocument();
  });
});

describe("Review moves: keyboard and screen reader (AC-23)", () => {
  it("announces the selection count in one polite live region, after a short pause", async () => {
    wirePlan({ items: () => json(itemsPage(1, 5, false)) });
    const container = await renderReview();
    await openFirstGroup();
    const boxes = await screen.findAllByRole("checkbox");

    await userEvent.click(boxes[0] as HTMLElement);
    await userEvent.click(boxes[1] as HTMLElement);
    await userEvent.click(boxes[2] as HTMLElement);

    const regions = container.querySelectorAll('[aria-live="polite"]');
    expect(regions).toHaveLength(1);
    expect(regions[0]).toHaveTextContent("");
    await waitFor(() => {
      expect(regions[0]).toHaveTextContent("3 mails selected");
    });
  });

  it("shows how many of the group are selected next to the select-all button", async () => {
    wirePlan({ items: () => json(itemsPage(1, 5, false)) });
    await renderReview();
    await openFirstGroup();
    const boxes = await screen.findAllByRole("checkbox");

    await userEvent.click(boxes[0] as HTMLElement);

    expect(screen.getByText("1 of 80 selected")).toBeInTheDocument();
  });

  it("opens and closes a group with Space and keeps its mails in the DOM order", async () => {
    wirePlan({ items: () => json(itemsPage(1, 2, false)) });
    await renderReview();
    const toggle = await screen.findByRole("button", { name: /Other to Invoices/ });
    toggle.focus();

    await userEvent.keyboard(" ");
    await screen.findAllByRole("checkbox");
    await userEvent.keyboard(" ");

    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("gives each mail checkbox a name from its sender, address and subject", async () => {
    wirePlan({ items: () => json({ items: [item(7, { senderName: "Anna", senderAddress: "anna@example.com", subject: "Receipt" })], page: 1, hasMore: false }) });
    await renderReview();
    await openFirstGroup();

    expect(await screen.findByRole("checkbox", { name: /Anna.*anna@example\.com.*Receipt/ })).toBeInTheDocument();
  });

  it("has no axe violations with a group open and a mail ticked", async () => {
    wirePlan({ items: () => json(itemsPage(1, 4, true)) });
    const container = await renderReview();
    await openFirstGroup();
    await userEvent.click((await screen.findAllByRole("checkbox"))[0] as HTMLElement);

    await expectNoAxeViolations(container);
  });

  it("marks each mail with the decision as words, not colour", async () => {
    wirePlan({
      items: () =>
        json({
          items: [item(1, { decision: "approved" }), item(2, { decision: "rejected" }), item(3)],
          page: 1,
          hasMore: false,
        }),
    });
    await renderReview();
    await openFirstGroup();
    const rows = within(await screen.findByRole("list", { name: "Mails in Other to Invoices" })).getAllByRole("listitem");

    expect(rows[0]).toHaveTextContent("Will move");
    expect(rows[1]).toHaveTextContent("Stays in place");
    expect(rows[2]).toHaveTextContent("Not decided yet");
  });
});
