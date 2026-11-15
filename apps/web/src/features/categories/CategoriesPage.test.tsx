import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { expectNoAxeViolations } from "@/test/axe";
import { INVOICES, LIST, json, renderPage, wire } from "@/test/categories";

afterEach(() => {
  vi.unstubAllGlobals();
});

async function loaded(): Promise<HTMLElement> {
  const container = renderPage();
  await screen.findByRole("heading", { level: 1, name: "Categories" });
  await screen.findByDisplayValue(INVOICES.name);
  return container;
}

describe("Categories page: reading the list", () => {
  it("given the loaded list, then name, description, counts, Other and the R1 text are shown (AC-1)", async () => {
    wire();
    await loaded();

    const cards = screen.getAllByRole("group", { name: /^Category \d+$/ });
    expect(cards).toHaveLength(2);
    const first = within(cards[0]!);
    expect(first.getByLabelText("Name")).toHaveValue("Invoices");
    expect(first.getByLabelText("Description")).toHaveValue("Invoices, receipts and payment confirmations.");
    expect(first.getByText("12 mails")).toBeInTheDocument();
    expect(within(cards[1]!).getByText("1 mail")).toBeInTheDocument();
    const other = screen.getByRole("group", { name: "Other" });
    expect(within(other).getByText("Mail that fits no category")).toBeInTheDocument();
    expect(within(other).getByText("7 mails")).toBeInTheDocument();
    expect(screen.getByText(/Old mail stays where it is for now\./)).toBeInTheDocument();
    expect(screen.getByText(/Changes apply to new mail from now on\./)).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "The model reads the description. Say what belongs here, for example: Invoices, receipts and payment confirmations.",
      ),
    ).not.toHaveLength(0);
    expect(screen.getByText("Mail you put in the Gmail label Archive is never re-sorted.")).toBeInTheDocument();
    expect(screen.getByText("Renaming only changes the label name.")).toBeInTheDocument();
    expect(document.title).toBe("Categories - Mail Assistant");
  });

  it("given the request is pending, then a skeleton with a busy status shows", () => {
    wire({ get: () => new Promise<Response>(() => undefined) });
    renderPage();
    expect(screen.getByText("Loading your categories")).toBeInTheDocument();
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(document.querySelectorAll("[data-skeleton]").length).toBeGreaterThan(0);
  });

  it("given the load fails, then a friendly banner offers Try again", async () => {
    let calls = 0;
    wire({ get: () => (++calls === 1 ? json({}, 500) : json(LIST)) });
    renderPage();
    expect(await screen.findByText("Could not load your categories.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByDisplayValue("Invoices")).toBeInTheDocument();
  });

  it("given the agent has not written the first list, then the page says it is not ready and shows no form", async () => {
    wire({ get: () => json({ ...LIST, version: 0, ready: false, categories: [] }) });
    renderPage();
    expect(await screen.findByText("Your categories are not ready yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
  });

  it("given a 429 on the read, then it says to wait", async () => {
    wire({ get: () => json({}, 429, { "Retry-After": "60" }) });
    renderPage();
    expect(await screen.findByText("Too many requests.")).toBeInTheDocument();
  });

  it("given names with markup, then they render as text and never as elements (AC-21)", async () => {
    const markup = "<img src=x onerror=alert(1)>";
    wire({
      get: () =>
        json({
          ...LIST,
          categories: [{ ...INVOICES, name: markup, description: "<b>bold</b>" }],
          olderCategories: [{ labelName: "Assistant/<i>old</i>", mailCount: 3 }],
        }),
    });
    const container = renderPage();
    expect(await screen.findByDisplayValue(markup)).toBeInTheDocument();
    expect(screen.getByDisplayValue("<b>bold</b>")).toBeInTheDocument();
    expect(screen.getByText("<i>old</i>")).toBeInTheDocument();
    expect(container.querySelector("img, b, i")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: `Delete ${markup}` }));
    expect(await screen.findByText(`Removed ${markup}.`)).toBeInTheDocument();
    expect(container.querySelector("img, b, i")).toBeNull();
  });
});

describe("Categories page: older categories", () => {
  it("given an older category, when Add to my list is pressed, then it becomes a card and focus goes to its description (AC-53)", async () => {
    wire();
    await loaded();
    const older = screen.getByRole("region", { name: "Older category" });
    expect(within(older).getByText("Travel")).toBeInTheDocument();

    await userEvent.click(within(older).getByRole("button", { name: "Add Travel to my list" }));

    const cards = screen.getAllByRole("group", { name: /^Category \d+$/ });
    expect(cards).toHaveLength(3);
    expect(within(cards[2]!).getByLabelText("Name")).toHaveValue("Travel");
    expect(within(cards[2]!).getByLabelText("Description")).toHaveFocus();
    expect(screen.queryByRole("region", { name: "Older category" })).not.toBeInTheDocument();
  });
});

describe("Categories page: accessibility of the loaded list", () => {
  it("has no axe violations", async () => {
    wire();
    const container = await loaded();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Add category" })).toBeInTheDocument();
    });
    await expectNoAxeViolations(container);
  });
});
