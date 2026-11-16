import { act, screen, waitFor, within } from "@testing-library/react";
import type { BoundFunctions, queries } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setCsrfToken } from "@/api/client";
import { expectNoAxeViolations } from "@/test/axe";
import { INVOICES, LIST, NEWS, json, renderPage, renderPageInRouter, wire } from "@/test/categories";

const TOKEN = "csrf-secret-4711";

beforeEach(() => {
  setCsrfToken(TOKEN);
});

afterEach(() => {
  setCsrfToken(null);
  vi.unstubAllGlobals();
});

async function loaded(): Promise<HTMLElement> {
  const container = renderPage();
  await screen.findByDisplayValue(INVOICES.name);
  return container;
}

function card(position: number): BoundFunctions<typeof queries> {
  return within(screen.getByRole("group", { name: `Category ${String(position)}` }));
}

async function rename(position: number, name: string): Promise<void> {
  const field = card(position).getByLabelText("Name");
  await userEvent.clear(field);
  if (name !== "") {
    await userEvent.type(field, name);
  }
}

const saveButton = (): HTMLElement => screen.getByRole("button", { name: "Save changes" });

describe("Categories page: saving", () => {
  it("given nothing changed, then Save is disabled", async () => {
    wire();
    await loaded();
    expect(saveButton()).toBeDisabled();
  });

  it("given edits, then the save bar counts them and sticks to the bottom below sm only", async () => {
    wire();
    await loaded();
    const bar = saveButton().closest("[data-save-bar]");
    expect(bar).toHaveClass("sticky", "bottom-0", "sm:static");
    expect(within(bar as HTMLElement).queryByText(/not saved/)).not.toBeInTheDocument();

    await rename(1, "Bills");
    expect(within(bar as HTMLElement).getByText("1 change not saved")).toBeInTheDocument();
    await userEvent.type(card(2).getByLabelText("Description"), " More");
    expect(within(bar as HTMLElement).getByText("2 changes not saved")).toBeInTheDocument();
  });

  it("given a rename, when Save is pressed, then a summary asks first and Keep editing returns focus to Save", async () => {
    const seen = wire();
    await loaded();
    await rename(1, "Bills");

    await userEvent.click(saveButton());

    const dialog = await screen.findByRole("alertdialog", { name: "Save 1 change?" });
    expect(within(dialog).getByText(/Renaming only changes the label name\./)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Keep editing" })).toHaveFocus();
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep editing" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(saveButton()).toHaveFocus();
    expect(seen.puts).toHaveLength(0);
  });

  it("given several changes, then the summary lists each one by name and says the filing rule once, only with a rename", async () => {
    wire();
    await loaded();
    await rename(1, "Bills");
    await userEvent.type(card(2).getByLabelText("Description"), " More");
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));
    await userEvent.type(card(3).getByLabelText("Name"), "Travel");
    await userEvent.type(card(3).getByLabelText("Description"), "Flights");
    await userEvent.click(saveButton());

    const dialog = await screen.findByRole("alertdialog", { name: "Save 3 changes?" });
    const items = within(dialog).getAllByRole("listitem").map((item) => item.textContent);
    expect(items).toEqual([
      'Rename "Invoices" to "Bills"',
      'Change the description of "Newsletters"',
      'Add "Travel"',
    ]);
    expect(within(dialog).getByText("Renaming only changes the label name.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Save changes" })).toBeInTheDocument();
    expect(screen.getAllByText(/new mail is filed using this list\. Mail already filed stays where it is\./)).toHaveLength(1);
    expect(within(dialog).queryByText(/new mail is filed/)).not.toBeInTheDocument();
  });

  it("given a removal and no rename, then the summary names it and has no renaming sentence", async () => {
    wire();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Delete Newsletters" }));
    await userEvent.click(saveButton());

    const dialog = await screen.findByRole("alertdialog", { name: "Save 1 change?" });
    expect(within(dialog).getByText('Remove "Newsletters"')).toBeInTheDocument();
    expect(within(dialog).queryByText(/Renaming only/)).not.toBeInTheDocument();
  });

  it("given a confirmed save, then the whole list goes on the stored version with the token and the page says Saved", async () => {
    const seen = wire({
      put: () => json({ ...LIST, version: 4, categories: [{ ...INVOICES, name: "Bills" }, NEWS] }),
    });
    await loaded();
    await rename(1, "Bills");
    await userEvent.click(saveButton());
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(seen.puts).toEqual([
      {
        token: TOKEN,
        body: {
          version: 3,
          categories: [
            { id: INVOICES.id, name: "Bills", description: INVOICES.description },
            { id: NEWS.id, name: NEWS.name, description: NEWS.description },
          ],
        },
      },
    ]);
    expect(card(1).getByLabelText("Name")).toHaveValue("Bills");
    expect(saveButton()).toBeDisabled();
  });

  it("given a deleted card and an older category added, then the body leaves out the deleted id and sends the new card without one", async () => {
    const seen = wire();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Delete Newsletters" }));
    await userEvent.click(screen.getByRole("button", { name: "Add to my list: Travel" }));
    await userEvent.type(card(2).getByLabelText("Description"), "Flights and hotels");
    await userEvent.click(saveButton());
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(seen.puts).toHaveLength(1);
    });
    expect(seen.puts[0]?.body.categories).toEqual([
      { id: INVOICES.id, name: "Invoices", description: INVOICES.description },
      { name: "Travel", description: "Flights and hotels" },
    ]);
  });

  it("given a deleted card, then the removed notice stands where the card was and says what saving does", async () => {
    wire();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Delete Invoices" }));

    const items = screen.getAllByRole("listitem");
    const notice = within(items[0] as HTMLElement);
    expect(notice.getByRole("status")).toHaveTextContent("Removed Invoices.");
    expect(notice.getByText(/It is removed when you save\. Mail already filed under it stays where it is\./)).toBeInTheDocument();
    expect(notice.getByRole("button", { name: "Undo" })).toBeInTheDocument();
    expect(within(items[1] as HTMLElement).getByLabelText("Name")).toHaveValue("Newsletters");
  });

  it("given a deleted card, when Undo is pressed, then it is back where it was", async () => {
    wire();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Delete Invoices" }));
    expect(screen.queryByDisplayValue("Invoices")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(card(1).getByLabelText("Name")).toHaveValue("Invoices");
    expect(saveButton()).toBeDisabled();
  });
});

describe("Categories page: leaving with unsaved changes", () => {
  function setUp(): ReturnType<typeof renderPageInRouter> {
    return renderPageInRouter();
  }

  it("given unsaved edits, when the user navigates away, then a dialog asks and Keep editing stays on the page", async () => {
    wire();
    const { router } = setUp();
    await screen.findByDisplayValue(INVOICES.name);
    await rename(1, "Bills");

    await act(async () => {
      await router.navigate("/elsewhere");
    });

    const dialog = await screen.findByRole("alertdialog", { name: "You have changes that are not saved. Leave without saving?" });
    expect(within(dialog).getByRole("button", { name: "Keep editing" })).toHaveFocus();
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep editing" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(card(1).getByLabelText("Name")).toHaveValue("Bills");
    expect(router.state.location.pathname).toBe("/categories");
  });

  it("given the dialog, when Leave is pressed, then the navigation goes through", async () => {
    wire();
    const { router } = setUp();
    await screen.findByDisplayValue(INVOICES.name);
    await rename(1, "Bills");
    await act(async () => {
      await router.navigate("/elsewhere");
    });
    await userEvent.click(await screen.findByRole("button", { name: "Leave" }));
    expect(await screen.findByText("Elsewhere page")).toBeInTheDocument();
  });

  it("given no edits, then navigating away is not asked about", async () => {
    wire();
    const { router } = setUp();
    await screen.findByDisplayValue(INVOICES.name);
    await act(async () => {
      await router.navigate("/elsewhere");
    });
    expect(await screen.findByText("Elsewhere page")).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("given unsaved edits, then closing the tab asks the browser to confirm; without edits it does not", async () => {
    wire();
    setUp();
    await screen.findByDisplayValue(INVOICES.name);
    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);

    await rename(1, "Bills");
    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
  });
});

describe("Categories page: invalid fields (AC-2)", () => {
  it("given an adopted card without a description, when saving, then the error with the mark shows by the field, focus moves to it and nothing is sent", async () => {
    const seen = wire();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Add to my list: Travel" }));
    await rename(1, "");

    await userEvent.click(saveButton());

    const name = card(1).getByLabelText("Name");
    expect(name).toBeInvalid();
    expect(name).toHaveFocus();
    expect(card(1).getByText("Give the category a name.")).toBeInTheDocument();
    expect(card(3).getByLabelText("Description")).toBeInvalid();
    expect(card(3).getByText("Say what belongs in this category.")).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(seen.puts).toHaveLength(0);
  });

  it("given a name that is already used, then the error names the rule", async () => {
    wire();
    await loaded();
    await rename(2, "invoices");
    await userEvent.click(saveButton());
    expect(card(2).getByText("Another category already has this name.")).toBeInTheDocument();
    expect(card(2).getByLabelText("Name")).toHaveFocus();
  });

  it("given a typed name that is an older category, when saving, then the page does not refuse it and the save is asked for", async () => {
    const seen = wire();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));
    await userEvent.type(card(3).getByLabelText("Name"), "travel");
    await userEvent.type(card(3).getByLabelText("Description"), "Flights and hotels");

    await userEvent.click(saveButton());

    expect(await screen.findByRole("alertdialog", { name: "Save 1 change?" })).toBeInTheDocument();
    expect(screen.queryByText("A Gmail label with this name already exists.")).not.toBeInTheDocument();
    expect(seen.puts).toHaveLength(0);
  });

  it("given the api refuses a field (422), then the error shows next to that field and focus moves there", async () => {
    wire({
      put: () =>
        json(
          {
            type: "about:blank",
            title: "Unprocessable",
            status: 422,
            problems: [{ rule: "name_label_exists", field: "name", index: 1 }],
          },
          422,
        ),
    });
    await loaded();
    await rename(2, "Trips");
    await userEvent.click(saveButton());
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("A Gmail label with this name already exists.")).toBeInTheDocument();
    await waitFor(() => {
      expect(card(2).getByLabelText("Name")).toHaveFocus();
    });
    expect(card(2).getByLabelText("Name")).toBeInvalid();
  });

  it("has no axe violations with errors shown", async () => {
    wire();
    const container = await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));
    await userEvent.click(saveButton());
    await screen.findAllByRole("alert");
    await expectNoAxeViolations(container);
  });
});

describe("Categories page: a save that does not store", () => {
  async function save(): Promise<void> {
    await rename(1, "Bills");
    await userEvent.click(saveButton());
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Save changes" }));
  }

  it("given a conflict (409), then the banner has the focus and the newest list is shown (AC-3)", async () => {
    const newest = { ...LIST, version: 4, categories: [{ ...INVOICES, name: "Receipts" }, NEWS] };
    wire({ put: () => json({ type: "x", title: "Conflict", status: 409, reason: "version", current: newest }, 409) });
    await loaded();
    await save();

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("The list changed somewhere else.");
    await waitFor(() => {
      expect(banner).toHaveFocus();
    });
    expect(card(1).getByLabelText("Name")).toHaveValue("Receipts");
  });

  it("given a 409 not-ready, then the page shows the not-ready state", async () => {
    const current = { ...LIST, version: 0, ready: false, categories: [] };
    wire({ put: () => json({ type: "x", title: "Conflict", status: 409, reason: "not-ready", current }, 409) });
    await loaded();
    await save();
    expect(await screen.findByText("Your categories are not ready yet.")).toBeInTheDocument();
  });

  it("given a 429, then it says too many saves", async () => {
    wire({ put: () => json({}, 429, { "Retry-After": "60" }) });
    await loaded();
    await save();
    expect(await screen.findByText("Too many saves.")).toBeInTheDocument();
    expect(screen.getByText("Wait a minute and try again.")).toBeInTheDocument();
    expect(card(1).getByLabelText("Name")).toHaveValue("Bills");
  });

  it("given a failed save, then it says nothing was changed and Try again saves again", async () => {
    let calls = 0;
    const seen = wire({ put: () => (++calls === 1 ? json({}, 500) : json({ ...LIST, version: 4 })) });
    await loaded();
    await save();
    expect(await screen.findByText("Could not save. Nothing was changed.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(seen.puts).toHaveLength(2);
  });

  it("given a save in flight, then Save says Saving and the fields are read-only", async () => {
    wire({ put: () => new Promise<Response>(() => undefined) });
    await loaded();
    await save();
    expect(await screen.findByRole("button", { name: "Saving..." })).toHaveAttribute("aria-busy", "true");
    expect(card(1).getByLabelText("Name")).toHaveAttribute("readonly");
  });
});

describe("Categories page: keyboard only (AC-23)", () => {
  it("lets a rename be typed, confirmed and saved without a pointer, and focus ends on the result", async () => {
    const seen = wire({ put: (body) => json({ ...LIST, version: body.version + 1, categories: [{ ...INVOICES, name: "Bills" }, NEWS] }) });
    await loaded();
    const user = userEvent.setup();
    await user.tab();
    while (document.activeElement !== card(1).getByLabelText("Name")) {
      await user.tab();
    }
    await user.keyboard("{Control>}a{/Control}Bills");
    while (document.activeElement !== saveButton()) {
      await user.tab();
    }
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("alertdialog");
    await user.tab();
    expect(within(dialog).getByRole("button", { name: "Save changes" })).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(seen.puts).toHaveLength(1);
    // Save is disabled again (nothing to save), so focus moves to the result, which is announced.
    await waitFor(() => {
      expect(screen.getByText("Saved.").closest('[role="status"]')).toHaveFocus();
    });
  });

  it("closes the summary with Escape and puts focus back on Save", async () => {
    wire();
    await loaded();
    await rename(1, "Bills");
    await userEvent.click(saveButton());
    await screen.findByRole("alertdialog");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(saveButton()).toHaveFocus();
  });
});
