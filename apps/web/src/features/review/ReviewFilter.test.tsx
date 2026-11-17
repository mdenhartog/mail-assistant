import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { setCsrfToken } from "@/api/client";
import { expectNoAxeViolations } from "@/test/axe";
import { json } from "@/test/categories";
import { item, itemsPage, wirePlan } from "@/test/plan";
import { renderReview } from "@/test/review";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  setCsrfToken(null);
  window.localStorage.clear();
  window.sessionStorage.clear();
});

const ANNA = [
  item(11, { senderName: "Anna", senderAddress: "anna@example.com", subject: "Zebra" }),
  item(12, { senderName: "Annabel", senderAddress: "annabel@example.com", subject: "Apple" }),
];

function senderOf(body: unknown): string {
  return typeof body === "object" && body !== null && "sender" in body ? String(body.sender) : "";
}

function searchBy(rows = ANNA): (body: unknown) => Response {
  return (body) =>
    senderOf(body).toLowerCase() === "anna" ? json({ items: rows, page: 1, hasMore: false }) : json({ items: [], page: 1, hasMore: false });
}

async function openGroup(): Promise<void> {
  await userEvent.click(await screen.findByRole("button", { name: /^Other to Invoices/ }));
  await screen.findAllByRole("checkbox");
}

async function typeSender(text: string): Promise<void> {
  await userEvent.type(screen.getByRole("searchbox", { name: "Search by sender" }), text);
}

describe("Review moves: filter and sort (AC-59)", () => {
  it("labels a sender search and a sort choice above the mails, both reachable with the keyboard", async () => {
    wirePlan();
    await renderReview();
    await openGroup();

    const search = screen.getByRole("searchbox", { name: "Search by sender" });
    const sort = screen.getByRole("combobox", { name: "Sort mails" });
    const options = within(sort)
      .getAllByRole("option")
      .map((option) => option.textContent);
    expect(options).toEqual(["Default order", "Sender A to Z", "Sender Z to A", "Subject A to Z", "Subject Z to A"]);
    search.focus();
    await userEvent.tab();
    expect(sort).toHaveFocus();
  });

  it("given a typed sender, then after a short pause only the matching mails show, and the count says how many", async () => {
    setCsrfToken("tok");
    const seen = wirePlan({ search: searchBy() });
    await renderReview();
    await openGroup();

    await typeSender("anna");

    expect(await screen.findByText("2 mails match")).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox")).toHaveLength(2);
    const posts = seen.filter((call) => call.path === "/api/plan/items/search");
    expect(posts).toHaveLength(1);
    expect(posts[0]?.body).toMatchObject({ sender: "anna", page: 1 });
    expect(posts[0]?.token).toBe("tok");
  });

  it("given a sort choice, then the mails show in the order the server returns for it", async () => {
    const seen = wirePlan({ search: () => json({ items: [...ANNA].reverse(), page: 1, hasMore: false }) });
    await renderReview();
    await openGroup();

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Sort mails" }), "Subject Z to A");

    await waitFor(() => {
      expect(screen.getAllByRole("checkbox")[0]).toHaveAccessibleName(/Annabel/);
    });
    expect(seen.at(-1)?.body).toMatchObject({ sort: "subject", order: "desc" });
  });

  it("given no match, then the group says no mail from that sender is in it", async () => {
    wirePlan({ search: searchBy() });
    await renderReview();
    await openGroup();

    await typeSender("zed");

    expect(await screen.findByText("No mail from that sender in this group")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("clears the search with its button, and the whole group shows again", async () => {
    wirePlan({ search: searchBy() });
    await renderReview();
    await openGroup();
    await typeSender("anna");
    await screen.findByText("2 mails match");

    await userEvent.click(screen.getByRole("button", { name: "Clear search" }));

    expect(screen.getByRole("searchbox", { name: "Search by sender" })).toHaveValue("");
    await waitFor(() => {
      expect(screen.getAllByRole("checkbox")).toHaveLength(3);
    });
    expect(screen.queryByText(/mails? match/)).not.toBeInTheDocument();
  });

  it("given the search fails, then it says so and Try again asks again", async () => {
    let calls = 0;
    wirePlan({ search: () => (++calls === 1 ? json({}, 500) : json({ items: ANNA, page: 1, hasMore: false })) });
    await renderReview();
    await openGroup();
    await typeSender("anna");

    expect(await screen.findByText("Could not load these mails.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("2 mails match")).toBeInTheDocument();
  });

  it("given a filter, then Select all names how many mails match first and selects only them after the user agrees", async () => {
    const decisions: unknown[] = [];
    wirePlan({
      search: searchBy(),
      decisions: (body) => {
        decisions.push(body);
        return json({ changed: 2 });
      },
    });
    await renderReview();
    await openGroup();
    await typeSender("anna");
    await screen.findByText("2 mails match");

    expect(screen.queryByRole("button", { name: /Select all 80/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Select the mails that match" }));
    expect(await screen.findByText("Select all 2 mails that match?")).toBeInTheDocument();
    expect(screen.getByText("0 of 80 selected")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Select these 2 mails" }));

    expect(screen.getByText("2 of 80 selected")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Approve selected (2)" }));
    await waitFor(() => {
      expect(decisions).toHaveLength(1);
    });
    expect(decisions[0]).toMatchObject({ scope: { ids: [11, 12] }, decision: "approved" });
  });

  it("lets the user back out of the select-all question without selecting anything", async () => {
    wirePlan({ search: searchBy() });
    await renderReview();
    await openGroup();
    await typeSender("anna");
    await screen.findByText("2 mails match");
    await userEvent.click(screen.getByRole("button", { name: "Select the mails that match" }));
    await screen.findByText("Select all 2 mails that match?");

    await userEvent.click(screen.getByRole("button", { name: "Not now" }));

    expect(screen.queryByText("Select all 2 mails that match?")).not.toBeInTheDocument();
    expect(screen.getByText("0 of 80 selected")).toBeInTheDocument();
  });

  it("never puts the sender text in a URL, in storage or in the console", async () => {
    const log = vi.spyOn(console, "log");
    const seen = wirePlan({ search: searchBy() });
    await renderReview();
    await openGroup();
    await typeSender("anna");
    await screen.findByText("2 mails match");

    for (const call of seen) {
      expect(`${call.path}?${call.search.toString()}`).not.toMatch(/anna/i);
    }
    expect(window.location.href).not.toMatch(/anna/i);
    expect(JSON.stringify(Object.entries(window.localStorage))).not.toMatch(/anna/i);
    expect(JSON.stringify(Object.entries(window.sessionStorage))).not.toMatch(/anna/i);
    expect(log).not.toHaveBeenCalled();
  });

  it("has no axe violations with a filter applied", async () => {
    wirePlan({ search: searchBy(), items: () => json(itemsPage(1, 3, false)) });
    const container = await renderReview();
    await openGroup();
    await typeSender("anna");
    await screen.findByText("2 mails match");

    await expectNoAxeViolations(container);
  });
});
