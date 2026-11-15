import { screen, waitFor, within } from "@testing-library/react";
import type { BoundFunctions, queries } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setCsrfToken } from "@/api/client";
import { expectNoAxeViolations } from "@/test/axe";
import { INVOICES, LIST, NEWS, json, renderPage, wire } from "@/test/categories";

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

  it("given a rename, when Save is pressed, then a summary asks first and Keep editing returns focus to Save", async () => {
    const seen = wire();
    await loaded();
    await rename(1, "Bills");

    await userEvent.click(saveButton());

    const dialog = await screen.findByRole("alertdialog", { name: "Save these changes?" });
    expect(within(dialog).getByText(/Renaming only changes the label name\./)).toBeInTheDocument();
    expect(within(dialog).getByText(/1 renamed/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Keep editing" })).toHaveFocus();
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep editing" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(saveButton()).toHaveFocus();
    expect(seen.puts).toHaveLength(0);
  });

  it("given a confirmed save, then the whole list goes on the stored version with the token and the page says Saved", async () => {
    const seen = wire({
      put: () => json({ ...LIST, version: 4, categories: [{ ...INVOICES, name: "Bills" }, NEWS] }),
    });
    await loaded();
    await rename(1, "Bills");
    await userEvent.click(saveButton());
    await userEvent.click(await screen.findByRole("button", { name: "Save" }));

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
    await userEvent.click(screen.getByRole("button", { name: "Add Travel to my list" }));
    await userEvent.type(card(2).getByLabelText("Description"), "Flights and hotels");
    await userEvent.click(saveButton());
    await userEvent.click(await screen.findByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(seen.puts).toHaveLength(1);
    });
    expect(seen.puts[0]?.body.categories).toEqual([
      { id: INVOICES.id, name: "Invoices", description: INVOICES.description },
      { name: "Travel", description: "Flights and hotels" },
    ]);
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

describe("Categories page: invalid fields (AC-2)", () => {
  it("given an adopted card without a description, when saving, then the error with the mark shows by the field, focus moves to it and nothing is sent", async () => {
    const seen = wire();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Add Travel to my list" }));
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
    await userEvent.click(await screen.findByRole("button", { name: "Save" }));

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
    await userEvent.click(await screen.findByRole("button", { name: "Save" }));
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
    expect(within(dialog).getByRole("button", { name: "Save" })).toHaveFocus();
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
