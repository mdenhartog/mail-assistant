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

    expect(screen.getAllByRole("group", { name: /^Category \d+$/ })).toHaveLength(2);
    const first = within(screen.getByRole("group", { name: "Category 1" }));
    expect(first.getByLabelText("Name")).toHaveValue("Invoices");
    expect(first.getByLabelText("Description")).toHaveValue("Invoices, receipts and payment confirmations.");
    expect(first.getByText("12 mails")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Category 2" })).getByText("1 mail")).toBeInTheDocument();
    const other = screen.getByRole("group", { name: "Other" });
    expect(within(other).getByText("Mail that fits no category")).toBeInTheDocument();
    expect(within(other).getByText("7 mails")).toBeInTheDocument();
    expect(screen.getAllByText(/new mail is filed using this list\. Mail already filed stays where it is\./)).toHaveLength(1);
    expect(
      screen.getAllByText(
        "The model reads the description. Say what belongs here, for example: Invoices, receipts and payment confirmations.",
      ),
    ).not.toHaveLength(0);
    expect(screen.getByText("Mail you put in the Gmail label Archive is never re-sorted.")).toBeInTheDocument();
    expect(screen.queryByText("Renaming only changes the label name.")).not.toBeInTheDocument();
    expect(document.title).toBe("Categories - Mail Assistant");
  });

  it("given the request is pending, then a skeleton with a busy status shows", () => {
    wire({ get: () => new Promise<Response>(() => undefined) });
    renderPage();
    expect(screen.getByRole("status")).toHaveTextContent("Loading your categories");
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

  it("given the agent has not written the first list, then the page says it is being set up and Check again reads the list again", async () => {
    let calls = 0;
    wire({ get: () => (++calls === 1 ? json({ ...LIST, version: 0, ready: false, categories: [] }) : json(LIST)) });
    renderPage();
    expect(await screen.findByText("Your categories are still being set up.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Check again" }));

    expect(await screen.findByDisplayValue("Invoices")).toBeInTheDocument();
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

describe("Categories page: the limit", () => {
  it("given 50 categories, then Add category is disabled and the message says what to do", async () => {
    const many = Array.from({ length: 50 }, (_, index) => ({
      id: `7f0c1c2e-1b1e-4c52-9d0e-${String(index).padStart(12, "0")}`,
      name: `Category ${String(index)}`,
      description: "Something",
      mailCount: 0,
    }));
    wire({ get: () => json({ ...LIST, categories: many, olderCategories: [] }) });
    renderPage();
    await screen.findByDisplayValue("Category 0");
    expect(screen.getByRole("button", { name: "Add category" })).toBeDisabled();
    expect(screen.getByText("You have reached the limit of 50 categories. Remove one to add another.")).toBeInTheDocument();
  });
});

describe("Categories page: older categories", () => {
  it("given an older category, when Add to my list is pressed, then it becomes a card and focus goes to its description (AC-53)", async () => {
    wire();
    await loaded();
    const older = screen.getByRole("region", { name: "Older category" });
    expect(within(older).getByText("Travel")).toBeInTheDocument();
    expect(
      within(older).getByText(
        "These Gmail labels exist but are not on your list. Add one to use it for new mail. Its mails stay where they are, and you can write a description for it.",
      ),
    ).toBeInTheDocument();

    await userEvent.click(within(older).getByRole("button", { name: "Add to my list: Travel" }));

    expect(screen.getAllByRole("group", { name: /^Category \d+$/ })).toHaveLength(3);
    const added = within(screen.getByRole("group", { name: "Category 3" }));
    expect(added.getByLabelText("Name")).toHaveValue("Travel");
    expect(added.getByLabelText("Description")).toHaveFocus();
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
