import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CategoryItem } from "@/api/categories/categories.types";
import { expectNoAxeViolations } from "@/test/axe";
import { INVOICES, LIST, NEWS, json, renderPage, wire } from "@/test/categories";

afterEach(() => {
  vi.unstubAllGlobals();
});

async function loaded(): Promise<HTMLElement> {
  const container = renderPage();
  await screen.findByRole("heading", { level: 1, name: "Categories" });
  await screen.findByRole("button", { name: `Edit ${INVOICES.name}` });
  return container;
}

/** 43 categories under 8 parents, as the user's own list is nested. */
function nested(): CategoryItem[] {
  const parents = Array.from({ length: 8 }, (_, index) => `Group${String(index)}`);
  const children = parents.flatMap((parent) => Array.from({ length: 5 }, (_, child) => `${parent}/Topic${String(child)}`));
  return [...children, "Other things", "Loose", "Alone"].map((name, index) => ({
    id: `7f0c1c2e-1b1e-4c52-9d0e-${String(index).padStart(12, "0")}`,
    name,
    description: "Something",
    mailCount: index,
    kind: index % 2 === 0 ? ("topic" as const) : ("extra" as const),
    notify: index === 3,
    senders: index === 3 ? [{ entry: "a@x.nl", subdomains: false, skippedCount: 0 }] : [],
  }));
}

/** The list row (name button, kind, sender count and tick) that holds the button of this name. */
function rowOf(buttonName: string): HTMLElement {
  const row = screen.getByRole("button", { name: buttonName }).closest("[data-row-key]");
  if (!(row instanceof HTMLElement)) {
    throw new Error("no row");
  }
  return row;
}

const withNested = (): void => {
  wire({ get: () => json({ ...LIST, categories: nested(), olderCategories: [] }) });
};

describe("Categories page: the row button (AC-22)", () => {
  it("given a row, then the button holds only the visible name and the kind and sender count are its description", async () => {
    withNested();
    renderPage();
    const edit = await screen.findByRole("button", { name: "Edit Loose" });

    expect(edit).toHaveAccessibleDescription(/(Topic|Extra label).*(No senders|\d+ senders?)/);
    expect(edit).toHaveTextContent(/^Loose$/);
  });
});

describe("Categories page: the collapsed list (criterion 1, AC-64)", () => {
  it("given 43 nested categories, then parents are collapsed, with search and the filter, and every control is at least 44 px", async () => {
    withNested();
    renderPage();
    await screen.findByRole("button", { name: "Edit Loose" });

    expect(screen.getByRole("searchbox", { name: "Search categories" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Always notify only" })).not.toBeChecked();
    const expand = screen.getByRole("button", { name: "Expand Group0" });
    expect(expand).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "Edit Group0/Topic0" })).not.toBeInTheDocument();
    for (const control of [expand, screen.getByRole("button", { name: "Edit Loose" })]) {
      expect(control).toHaveClass("min-h-11");
    }
    expect(screen.getByRole("checkbox", { name: "Always notify, Loose" }).closest("label")).toHaveClass("min-h-11", "min-w-11");
  });

  it("given a collapsed parent, when expanded, then its children show one row each and Collapse hides them again", async () => {
    withNested();
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Expand Group0" }));

    expect(screen.getByRole("button", { name: "Collapse Group0" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Edit Group0/Topic0" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Group0/Topic4" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Collapse Group0" }));
    expect(screen.queryByRole("button", { name: "Edit Group0/Topic0" })).not.toBeInTheDocument();
  });

  it("given a row, then it shows the name, the kind as a word, the sender count and no sender text", async () => {
    wire();
    await loaded();
    const row = within(rowOf("Edit Invoices"));
    expect(row.getByText("Invoices")).toBeInTheDocument();
    expect(row.getByText("Extra label")).toBeInTheDocument();
    expect(row.getByText("1 sender")).toBeInTheDocument();
    const news = within(rowOf("Edit Newsletters"));
    expect(news.getByText("Topic")).toBeInTheDocument();
    expect(news.getByText("No senders")).toBeInTheDocument();
    expect(screen.queryByText("billing@example.com")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Senders" })).not.toBeInTheDocument();
  });

  it("given a search, then only matches show, with their parents open; clearing it brings the collapsed list back", async () => {
    withNested();
    renderPage();
    await userEvent.type(await screen.findByRole("searchbox", { name: "Search categories" }), "group3/topic2");

    expect(screen.getByRole("button", { name: "Edit Group3/Topic2" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit Group3/Topic1" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit Loose" })).not.toBeInTheDocument();
    await userEvent.clear(screen.getByRole("searchbox", { name: "Search categories" }));
    expect(screen.queryByRole("button", { name: "Edit Group3/Topic2" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Loose" })).toBeInTheDocument();
  });

  it("given a search without a match, then the page says so", async () => {
    wire();
    await loaded();
    await userEvent.type(screen.getByRole("searchbox", { name: "Search categories" }), "zzz");
    expect(screen.getByText("No category matches.")).toBeInTheDocument();
  });

  it("given the filter Always notify only, then only ticked categories show", async () => {
    wire();
    await loaded();
    await userEvent.click(screen.getByRole("checkbox", { name: "Always notify only" }));
    expect(screen.getByRole("button", { name: "Edit Invoices" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit Newsletters" })).not.toBeInTheDocument();
  });
});

describe("Categories page: the tick and the tree (criterion 6, AC-67)", () => {
  it("labels the tick with the full category name and counts the change until Save changes", async () => {
    wire();
    await loaded();
    const tick = screen.getByRole("checkbox", { name: "Always notify, Newsletters" });
    expect(tick).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Always notify, Invoices" })).toBeChecked();
    await userEvent.click(tick);
    expect(tick).toBeChecked();
    expect(screen.getByText("1 change not saved")).toBeInTheDocument();
  });

  it("uses real nested lists, and the tick of a child names its full path", async () => {
    withNested();
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Expand Group1" }));

    const child = screen.getByRole("button", { name: "Edit Group1/Topic2" }).closest("li");
    const parent = child?.parentElement?.closest("li");
    expect(child?.parentElement?.tagName).toBe("UL");
    expect(parent).not.toBeNull();
    expect(within(parent as HTMLElement).getByRole("button", { name: "Collapse Group1" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Always notify, Group1/Topic2" })).toBeInTheDocument();
  });

  it("has no axe violations, collapsed and expanded", async () => {
    withNested();
    const container = renderPage();
    await screen.findByRole("button", { name: "Expand Group1" });
    await expectNoAxeViolations(container);
    await userEvent.click(screen.getByRole("button", { name: "Expand Group1" }));
    await expectNoAxeViolations(container);
  });
});

describe("Categories page: the full-screen edit view (criterion 2)", () => {
  it("given a row, when tapped, then the edit view replaces the list with Save and Cancel and no sender editor was inline", async () => {
    wire();
    await loaded();
    expect(screen.queryByRole("textbox", { name: "Senders" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Edit Invoices" }));

    const view = within(screen.getByRole("region", { name: "Edit category" }));
    expect(view.getByLabelText("Name")).toHaveValue("Invoices");
    expect(view.getByLabelText("Senders")).toHaveValue("billing@example.com");
    expect(view.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(view.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Category list" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Categories" })).toBeInTheDocument();
  });

  it("given an edit, when Save is pressed, then the list is back with the change counted and focus on the row", async () => {
    wire();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Edit Newsletters" }));
    const view = within(screen.getByRole("region", { name: "Edit category" }));
    await userEvent.type(view.getByLabelText("Description"), " More");
    await userEvent.click(view.getByRole("button", { name: "Save" }));

    expect(screen.queryByRole("region", { name: "Edit category" })).not.toBeInTheDocument();
    expect(screen.getByText("1 change not saved")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Newsletters" })).toHaveFocus();
  });

  it("given an edit, when Cancel is pressed, then the category is as it was and nothing is unsaved", async () => {
    wire();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Edit Newsletters" }));
    const view = within(screen.getByRole("region", { name: "Edit category" }));
    await userEvent.type(view.getByLabelText("Name"), "x");
    await userEvent.click(view.getByRole("checkbox", { name: "Always notify" }));
    await userEvent.click(view.getByRole("button", { name: "Cancel" }));

    expect(screen.getByRole("button", { name: "Edit Newsletters" })).toBeInTheDocument();
    expect(screen.queryByText(/not saved/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  });
});

describe("Categories page: the fixed block and the help texts (criterion 4, AC-68)", () => {
  it("shows the explanation block, including the sentence that points at the Sort everything again button", async () => {
    wire();
    await loaded();
    expect(
      screen.getByText(
        "Changing the list never moves mail you already have. Only new mail follows it. To re-sort the inbox, press Sort everything again.",
      ),
    ).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Sort everything again" })).toBeInTheDocument();
    expect(screen.getByText("Your archive label is left alone.")).toBeInTheDocument();
  });

  it("shows the help text beside each field of the edit view, with the spec's words", async () => {
    wire();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Edit Invoices" }));
    const view = within(screen.getByRole("region", { name: "Edit category" }));

    expect(view.getByText("Every mail gets exactly one. If nothing fits, it goes to Other.")).toBeInTheDocument();
    expect(view.getByText("Added on top of the topic, at most one per mail.")).toBeInTheDocument();
    expect(
      view.getByText(
        /Mail from these addresses or domains goes here without the AI choosing the category, only when Gmail confirms the sender is real\. If Gmail cannot confirm it, the mail goes to the AI\./,
      ),
    ).toBeInTheDocument();
    expect(view.getByText("You get a Telegram message for every new mail here, urgent or not.")).toBeInTheDocument();
    expect(view.getByLabelText("Senders")).toHaveAccessibleDescription(/One entry per line.*\+subdomains/);
    expect(view.getByRole("checkbox", { name: "Always notify" })).toHaveAccessibleDescription(
      expect.stringContaining("You get a Telegram message for every new mail here, urgent or not."),
    );
    expect(view.getByRole("radio", { name: "Topic" })).toHaveAccessibleDescription(
      "Every mail gets exactly one. If nothing fits, it goes to Other.",
    );
  });

  it("has no axe violations in the edit view", async () => {
    wire();
    const container = await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Edit Invoices" }));
    await screen.findByRole("region", { name: "Edit category" });
    await expectNoAxeViolations(container);
  });
});

describe("Categories page: states (criterion 5)", () => {
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
    expect(await screen.findByRole("button", { name: "Edit Invoices" })).toBeInTheDocument();
  });

  it("given a 429 on the read, then it says to wait", async () => {
    wire({ get: () => json({}, 429, { "Retry-After": "60" }) });
    renderPage();
    expect(await screen.findByText("Too many requests.")).toBeInTheDocument();
  });

  it("given the agent has not written the first list, then the page says it is being set up and Check again reads the list again", async () => {
    let calls = 0;
    wire({ get: () => (++calls === 1 ? json({ ...LIST, version: 0, ready: false, categories: [] }) : json(LIST)) });
    renderPage();
    expect(await screen.findByText("Your categories are still being set up.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(await screen.findByRole("button", { name: "Edit Invoices" })).toBeInTheDocument();
  });

  it("given a ready list without categories, then the page says it is empty and offers Add category", async () => {
    wire({ get: () => json({ ...LIST, categories: [], olderCategories: [] }) });
    renderPage();
    expect(await screen.findByText("You have no categories yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add category" })).toBeEnabled();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
  });

  it("given 100 categories, then Add category is disabled and the message says what to do", async () => {
    const many = Array.from({ length: 100 }, (_, index) => ({
      ...NEWS,
      id: `7f0c1c2e-1b1e-4c52-9d0e-${String(index).padStart(12, "0")}`,
      name: `Category ${String(index)}`,
    }));
    wire({ get: () => json({ ...LIST, categories: many, olderCategories: [] }) });
    renderPage();
    await screen.findByRole("button", { name: "Edit Category 0" });
    expect(screen.getByRole("button", { name: "Add category" })).toBeDisabled();
    expect(screen.getByText("You have reached the limit of 100 categories. Remove one to add another.")).toBeInTheDocument();
  });

  it("given an older category, when Add to my list is pressed, then its edit view opens as a new category with the name filled in", async () => {
    wire();
    await loaded();
    const older = screen.getByRole("region", { name: "Older category" });
    await userEvent.click(within(older).getByRole("button", { name: "Add to my list: Travel" }));

    const view = within(screen.getByRole("region", { name: "New category" }));
    expect(view.getByLabelText("Name")).toHaveValue("Travel");
    expect(view.getByLabelText("Description")).toHaveFocus();
  });

  it("given Add category, then a new category opens in the edit view with focus on its name; Cancel drops it", async () => {
    wire();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));
    const view = within(screen.getByRole("region", { name: "New category" }));
    expect(view.getByLabelText("Name")).toHaveFocus();
    await userEvent.click(view.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText(/not saved/)).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Edit / })).toHaveLength(2);
  });
});

describe("Categories page: text is text (criterion 7)", () => {
  it("given names and descriptions with markup, then they render as text and never as elements", async () => {
    const markup = "<img src=x onerror=alert(1)>";
    wire({
      get: () =>
        json({
          ...LIST,
          categories: [{ ...INVOICES, name: markup, description: "<b>bold</b><script>alert(1)</script>" }],
          olderCategories: [{ labelName: "<i>old</i>", mailCount: 3 }],
        }),
    });
    const container = renderPage();
    expect(await screen.findByText(markup)).toBeInTheDocument();
    expect(screen.getByText("<i>old</i>")).toBeInTheDocument();
    expect(container.querySelector("img, b, i, script")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: `Edit ${markup}` }));
    expect(screen.getByLabelText("Description")).toHaveValue("<b>bold</b><script>alert(1)</script>");
    expect(container.querySelector("img, b, i, script")).toBeNull();
  });
});

describe("Categories page: the general instructions", () => {
  it("shows the instructions of the list with a count and the help text", async () => {
    wire();
    await loaded();
    const field = screen.getByLabelText("General instructions");
    expect(field).toHaveValue("Keep receipts for the tax year.");
    expect(screen.getByText("31 of 4000")).toBeInTheDocument();
    await waitFor(() => {
      expect(field).toHaveAccessibleDescription(/applies to the whole list/);
    });
  });
});
