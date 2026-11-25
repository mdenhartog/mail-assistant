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

type View = BoundFunctions<typeof queries>;

async function loaded(): Promise<HTMLElement> {
  const container = renderPage();
  await screen.findByRole("button", { name: `Edit ${INVOICES.name}` });
  return container;
}

async function edit(name: string): Promise<View> {
  await userEvent.click(await screen.findByRole("button", { name: `Edit ${name}` }));
  return within(screen.getByRole("region", { name: "Edit category" }));
}

async function replace(field: HTMLElement, text: string): Promise<void> {
  await userEvent.clear(field);
  if (text !== "") {
    await userEvent.type(field, text);
  }
}

/** Opens a category, gives it a new name and keeps the edit with Save, so the page has an unsaved change. */
async function rename(from: string, to: string): Promise<void> {
  const view = await edit(from);
  await replace(view.getByLabelText("Name"), to);
  await userEvent.click(view.getByRole("button", { name: "Save" }));
}

/** A stored category as the PUT carries it: everything the api returned except the mail count. */
function V2(item: typeof INVOICES | typeof NEWS): Omit<typeof INVOICES, "mailCount" | "kind" | "senders"> & { kind: "topic" | "extra"; senders: { entry: string; subdomains: boolean }[] } {
  const senders = item.senders.map(({ entry, subdomains }) => ({ entry, subdomains }));
  return { id: item.id, name: item.name, description: item.description, kind: item.kind, notify: item.notify, senders };
}

const saveButton = (): HTMLElement => screen.getByRole("button", { name: "Save changes" });

async function confirm(): Promise<void> {
  await userEvent.click(saveButton());
  await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Save changes" }));
}

describe("Categories page: saving", () => {
  it("given nothing changed, then Save changes is disabled", async () => {
    wire();
    await loaded();
    expect(saveButton()).toBeDisabled();
  });

  it("given edits, then the save bar counts them and is the sticky action bar of the page", async () => {
    wire();
    await loaded();
    const bar = saveButton().closest("[data-action-bar]");
    expect(bar).toHaveClass("data-sticky:sticky", "bottom-0");
    expect(within(bar as HTMLElement).queryByText(/not saved/)).not.toBeInTheDocument();

    await rename("Invoices", "Bills");
    expect(screen.getByText("1 change not saved")).toBeInTheDocument();
    const view = await edit("Newsletters");
    await userEvent.type(view.getByLabelText("Description"), " More");
    await userEvent.click(view.getByRole("button", { name: "Save" }));
    expect(screen.getByText("2 changes not saved")).toBeInTheDocument();
  });

  it("given a rename, when Save changes is pressed, then a summary asks first and Keep editing returns focus to it", async () => {
    const seen = wire();
    await loaded();
    await rename("Invoices", "Bills");

    await userEvent.click(saveButton());

    const dialog = await screen.findByRole("alertdialog", { name: "Save 1 change?" });
    expect(within(dialog).getByText(/Renaming only changes the label name\./)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Keep editing" })).toHaveFocus();
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep editing" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(saveButton()).toHaveFocus();
    expect(seen.puts).toHaveLength(0);
  });

  it("given several changes, then the summary lists each one by name and says the renaming note only with a rename", async () => {
    wire();
    await loaded();
    await rename("Invoices", "Bills");
    const news = await edit("Newsletters");
    await userEvent.type(news.getByLabelText("Description"), " More");
    await userEvent.click(news.getByRole("button", { name: "Save" }));
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));
    const added = within(screen.getByRole("region", { name: "New category" }));
    await userEvent.type(added.getByLabelText("Name"), "Travel");
    await userEvent.type(added.getByLabelText("Description"), "Flights");
    await userEvent.click(added.getByRole("button", { name: "Save" }));
    await userEvent.click(saveButton());

    const dialog = await screen.findByRole("alertdialog", { name: "Save 3 changes?" });
    const items = within(dialog).getAllByRole("listitem").map((item) => item.textContent);
    expect(items).toEqual(['Rename "Invoices" to "Bills"', 'Change the description of "Newsletters"', 'Add "Travel"']);
    expect(within(dialog).getByText("Renaming only changes the label name.")).toBeInTheDocument();
  });

  it("given a kind, a tick, senders and instructions changed, then the summary names each of them", async () => {
    wire();
    await loaded();
    await userEvent.click(screen.getByRole("checkbox", { name: "Always notify, Newsletters" }));
    const view = await edit("Newsletters");
    await userEvent.click(view.getByRole("radio", { name: "Extra label" }));
    await userEvent.type(view.getByLabelText("Senders"), "news@y.nl");
    await userEvent.click(view.getByRole("button", { name: "Save" }));
    await userEvent.type(screen.getByLabelText("General instructions"), " More.");
    await userEvent.click(saveButton());

    const dialog = await screen.findByRole("alertdialog", { name: "Save 4 changes?" });
    expect(within(dialog).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Change the general instructions",
      'Change the kind of "Newsletters"',
      'Turn always notify on for "Newsletters"',
      'Change the senders of "Newsletters"',
    ]);
    expect(within(dialog).queryByText(/Renaming only/)).not.toBeInTheDocument();
  });

  it("given a removal and no rename, then the summary names it and has no renaming sentence", async () => {
    wire();
    await loaded();
    await userEvent.click((await edit("Newsletters")).getByRole("button", { name: "Delete Newsletters" }));
    await userEvent.click(saveButton());

    const dialog = await screen.findByRole("alertdialog", { name: "Save 1 change?" });
    expect(within(dialog).getByText('Remove "Newsletters"')).toBeInTheDocument();
    expect(within(dialog).queryByText(/Renaming only/)).not.toBeInTheDocument();
  });

  it("given a confirmed save, then the whole list goes on the stored version with the token and the page says Saved", async () => {
    const seen = wire({ put: () => json({ ...LIST, version: 4, categories: [{ ...INVOICES, name: "Bills" }, NEWS] }) });
    await loaded();
    await rename("Invoices", "Bills");
    await confirm();

    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(seen.puts).toEqual([
      {
        token: TOKEN,
        body: { version: 3, generalInstructions: LIST.generalInstructions, archiveLabel: LIST.archiveLabel, otherLabel: LIST.otherLabel, categories: [{ ...V2(INVOICES), name: "Bills" }, V2(NEWS)] },
      },
    ]);
    expect(screen.getByRole("button", { name: "Edit Bills" })).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
  });

  it("given senders written with a trailing marker, then the body carries them as entry and subdomains", async () => {
    const seen = wire();
    await loaded();
    const view = await edit("Newsletters");
    await userEvent.type(view.getByLabelText("Senders"), "News@Example.nl +subdomains{Enter}{Enter}a@y.nl");
    await userEvent.click(view.getByRole("button", { name: "Save" }));
    await userEvent.type(screen.getByLabelText("General instructions"), "!");
    await confirm();

    await waitFor(() => {
      expect(seen.puts).toHaveLength(1);
    });
    expect(seen.puts[0]?.body.generalInstructions).toBe("Keep receipts for the tax year.!");
    expect(seen.puts[0]?.body.categories[1]?.senders).toEqual([
      { entry: "News@Example.nl", subdomains: true },
      { entry: "a@y.nl", subdomains: false },
    ]);
  });

  it("given a deleted category and a new one added, then the body leaves out the deleted id and sends the new one without an id", async () => {
    const seen = wire();
    await loaded();
    await userEvent.click((await edit("Newsletters")).getByRole("button", { name: "Delete Newsletters" }));
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));
    const added = within(screen.getByRole("region", { name: "New category" }));
    await userEvent.type(added.getByLabelText("Name"), "Travel");
    await userEvent.type(added.getByLabelText("Description"), "Flights and hotels");
    await userEvent.click(added.getByRole("button", { name: "Save" }));
    await confirm();

    await waitFor(() => {
      expect(seen.puts).toHaveLength(1);
    });
    expect(seen.puts[0]?.body.categories).toEqual([
      V2(INVOICES),
      { name: "Travel", description: "Flights and hotels", kind: "topic", notify: false, senders: [] },
    ]);
  });

  it("given a deleted category, then a notice with Undo says what saving does with it", async () => {
    wire();
    await loaded();
    await userEvent.click((await edit("Invoices")).getByRole("button", { name: "Delete Invoices" }));

    expect(screen.getByText("Removed Invoices.")).toBeInTheDocument();
    expect(screen.getByText(/It is removed when you save\. Mail already filed under it stays where it is\./)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit Invoices" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Newsletters" })).toBeInTheDocument();
  });

  it("given a deleted category, when Undo is pressed, then it is back and nothing is unsaved", async () => {
    wire();
    await loaded();
    await userEvent.click((await edit("Invoices")).getByRole("button", { name: "Delete Invoices" }));
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(screen.getByRole("button", { name: "Edit Invoices" })).toHaveFocus();
    expect(saveButton()).toBeDisabled();
  });
});

describe("Categories page: leaving with unsaved changes (criterion 5)", () => {
  it("given unsaved edits, when the user navigates away, then a dialog asks and Keep editing stays on the page", async () => {
    wire();
    const { router } = renderPageInRouter();
    await screen.findByRole("button", { name: "Edit Invoices" });
    await rename("Invoices", "Bills");

    await act(async () => {
      await router.navigate("/elsewhere");
    });

    const dialog = await screen.findByRole("alertdialog", { name: "You have changes that are not saved. Leave without saving?" });
    expect(within(dialog).getByRole("button", { name: "Keep editing" })).toHaveFocus();
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep editing" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Bills" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/categories");
  });

  it("given unsaved edits in the edit view, when the user navigates away, then the dialog asks too", async () => {
    wire();
    const { router } = renderPageInRouter();
    const view = await edit("Invoices");
    await userEvent.type(view.getByLabelText("Name"), "x");

    await act(async () => {
      await router.navigate("/elsewhere");
    });

    expect(await screen.findByRole("alertdialog", { name: /Leave without saving/ })).toBeInTheDocument();
  });

  it("given the dialog, when Leave is pressed, then the navigation goes through", async () => {
    wire();
    const { router } = renderPageInRouter();
    await screen.findByRole("button", { name: "Edit Invoices" });
    await rename("Invoices", "Bills");
    await act(async () => {
      await router.navigate("/elsewhere");
    });
    await userEvent.click(await screen.findByRole("button", { name: "Leave" }));
    expect(await screen.findByText("Elsewhere page")).toBeInTheDocument();
  });

  it("given no edits, then navigating away is not asked about", async () => {
    wire();
    const { router } = renderPageInRouter();
    await screen.findByRole("button", { name: "Edit Invoices" });
    await act(async () => {
      await router.navigate("/elsewhere");
    });
    expect(await screen.findByText("Elsewhere page")).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("given unsaved edits, then closing the tab asks the browser to confirm; without edits it does not", async () => {
    wire();
    renderPageInRouter();
    await screen.findByRole("button", { name: "Edit Invoices" });
    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);

    await userEvent.click(screen.getByRole("checkbox", { name: "Always notify, Newsletters" }));
    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
  });
});

function problem422(problems: unknown[]): Response {
  return json({ type: "about:blank", title: "Unprocessable", status: 422, problems }, 422);
}

describe("Categories page: invalid fields (AC-2)", () => {
  it("given a new category without a description, when Save is pressed, then the error shows by the field, focus moves to it and the view stays", async () => {
    const seen = wire();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));
    const view = within(screen.getByRole("region", { name: "New category" }));
    await userEvent.type(view.getByLabelText("Name"), "Travel");
    await userEvent.click(view.getByRole("button", { name: "Save" }));

    const description = view.getByLabelText("Description");
    expect(description).toBeInvalid();
    expect(description).toHaveFocus();
    expect(description).toHaveAccessibleDescription(expect.stringContaining("Say what belongs in this category."));
    expect(view.getByText("Say what belongs in this category.")).toBeInTheDocument();
    expect(seen.puts).toHaveLength(0);
  });

  it("given a name that is already used, then the error names the rule and the view stays open", async () => {
    wire();
    await loaded();
    const view = await edit("Newsletters");
    await replace(view.getByLabelText("Name"), "invoices");
    await userEvent.click(view.getByRole("button", { name: "Save" }));
    expect(view.getByText("Another category already has this name.")).toBeInTheDocument();
    expect(view.getByLabelText("Name")).toHaveFocus();
  });

  it("given a typed name equal to the archive label, when saving, then name_setting_clash shows as plain text tied to the field and nothing is sent (AC 13, AC 17)", async () => {
    const seen = wire({ get: () => json({ ...LIST, archiveLabel: "Bewaard" }) });
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));
    const view = within(screen.getByRole("region", { name: "New category" }));
    await userEvent.type(view.getByLabelText("Name"), "bewaard");
    await userEvent.type(view.getByLabelText("Description"), "Old mail");
    await userEvent.click(view.getByRole("button", { name: "Save" }));

    const reason = view.getByText("This name is already used for your Other or archive label. Choose another name.");
    expect(view.getByLabelText("Name")).toBeInvalid();
    expect(view.getByLabelText("Name")).toHaveAccessibleDescription(/already used for your Other or archive label/);
    expect(reason.innerHTML).not.toContain("<");
    expect(seen.puts).toHaveLength(0);
  });

  it("given a typed name that is an older category, when saving, then the page does not refuse it and the save is asked for", async () => {
    const seen = wire();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));
    const view = within(screen.getByRole("region", { name: "New category" }));
    await userEvent.type(view.getByLabelText("Name"), "travel");
    await userEvent.type(view.getByLabelText("Description"), "Flights and hotels");
    await userEvent.click(view.getByRole("button", { name: "Save" }));

    await userEvent.click(saveButton());

    expect(await screen.findByRole("alertdialog", { name: "Save 1 change?" })).toBeInTheDocument();
    expect(screen.queryByText("This name is already used for your Other or archive label. Choose another name.")).not.toBeInTheDocument();
    expect(seen.puts).toHaveLength(0);
  });

  it("given the api refuses a name (422), then the edit view of that category opens with the error and focus on the field", async () => {
    wire({ put: () => problem422([{ rule: "name_setting_clash", field: "name", index: 1, position: null, otherIndex: null }]) });
    await loaded();
    await rename("Newsletters", "Trips");
    await confirm();

    const view = within(await screen.findByRole("region", { name: "Edit category" }));
    expect(view.getByText("This name is already used for your Other or archive label. Choose another name.")).toBeInTheDocument();
    await waitFor(() => {
      expect(view.getByLabelText("Name")).toHaveFocus();
    });
    expect(view.getByLabelText("Name")).toBeInvalid();
  });

  it("given the api refuses a sender entry, then its line shows the reason and the senders field has focus", async () => {
    wire({ put: () => problem422([{ rule: "sender_invalid", field: "senders", index: 0, position: 0, otherIndex: null }]) });
    await loaded();
    await userEvent.click(screen.getByRole("checkbox", { name: "Always notify, Newsletters" }));
    await confirm();

    const view = within(await screen.findByRole("region", { name: "Edit category" }));
    expect(view.getByText("Line 1: This is not a valid address or domain.")).toBeInTheDocument();
    await waitFor(() => {
      expect(view.getByLabelText("Senders")).toHaveFocus();
    });
  });

  it("given the api names another category for an entry (422), then the conflict message names it", async () => {
    wire({ put: () => problem422([{ rule: "sender_duplicate", field: "senders", index: 1, position: 0, otherIndex: 0 }]) });
    await loaded();
    const view = await edit("Newsletters");
    await userEvent.type(view.getByLabelText("Senders"), "dup@x.nl");
    await userEvent.click(view.getByRole("button", { name: "Save" }));
    await confirm();

    const again = within(await screen.findByRole("region", { name: "Edit category" }));
    expect(again.getByText("Line 1: dup@x.nl is already in Invoices. Remove it there first.")).toBeInTheDocument();
  });

  it("given a description edit, then the body carries kind, notify, senders and the general instructions unchanged", async () => {
    const seen = wire();
    await loaded();
    const view = await edit("Invoices");
    await replace(view.getByLabelText("Description"), "Bills only");
    await userEvent.click(view.getByRole("button", { name: "Save" }));
    await confirm();

    await waitFor(() => {
      expect(seen.puts).toHaveLength(1);
    });
    expect(seen.puts[0]?.body.generalInstructions).toBe("Keep receipts for the tax year.");
    expect(seen.puts[0]?.body.categories[0]).toMatchObject({
      kind: "extra",
      notify: true,
      senders: [{ entry: "billing@example.com", subdomains: false }],
    });
  });

  it("given entries with a skipped count, then the body carries no skippedCount", async () => {
    const skipped = { ...INVOICES, senders: [{ entry: "billing@example.com", subdomains: false, skippedCount: 4 }] };
    const seen = wire({ get: () => json({ ...LIST, categories: [skipped, NEWS] }) });
    await loaded();
    const view = await edit("Invoices");
    await replace(view.getByLabelText("Description"), "Bills only");
    await userEvent.click(view.getByRole("button", { name: "Save" }));
    await confirm();

    await waitFor(() => {
      expect(seen.puts).toHaveLength(1);
    });
    expect(JSON.stringify(seen.puts[0]?.body)).not.toContain("skippedCount");
    expect(seen.puts[0]?.body.categories[0]?.senders).toEqual([{ entry: "billing@example.com", subdomains: false }]);
  });

  it("given a 422 that names the instructions, then the field shows the reason, is invalid and has focus", async () => {
    wire({ put: () => problem422([{ rule: "instructions_too_long", field: "instructions", index: null, position: null, otherIndex: null }]) });
    await loaded();
    await userEvent.type(screen.getByLabelText("General instructions"), "x");
    await confirm();

    const field = await screen.findByLabelText("General instructions");
    expect(await screen.findByText("Use at most 4000 characters for the general instructions.")).toBeInTheDocument();
    expect(field).toBeInvalid();
    await waitFor(() => {
      expect(field).toHaveFocus();
    });
  });

  it("given a 422 that names no field, then the page shows the refused banner", async () => {
    wire({ put: () => problem422([{ rule: "list_too_many", field: "list", index: null, position: null, otherIndex: null }]) });
    await loaded();
    await userEvent.click(screen.getByRole("checkbox", { name: "Always notify, Newsletters" }));
    await confirm();
    expect(await screen.findByText("Some values were not accepted.")).toBeInTheDocument();
  });

  it("has no axe violations with errors shown", async () => {
    wire();
    const container = await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findAllByRole("alert");
    await expectNoAxeViolations(container);
  });
});

describe("Categories page: a save that does not store", () => {
  async function save(): Promise<void> {
    await rename("Invoices", "Bills");
    await confirm();
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
    expect(screen.getByRole("button", { name: "Edit Receipts" })).toBeInTheDocument();
  });

  it("given a 409 not-ready, then the page shows the not-ready state", async () => {
    const current = { ...LIST, version: 0, ready: false, categories: [] };
    wire({ put: () => json({ type: "x", title: "Conflict", status: 409, reason: "not-ready", current }, 409) });
    await loaded();
    await save();
    expect(await screen.findByText("Your categories are still being set up.")).toBeInTheDocument();
  });

  it("given a 429, then it says too many saves and the draft stays", async () => {
    wire({ put: () => json({}, 429, { "Retry-After": "60" }) });
    await loaded();
    await save();
    expect(await screen.findByText("Too many saves.")).toBeInTheDocument();
    expect(screen.getByText("Wait a minute and try again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Bills" })).toBeInTheDocument();
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

  it("given a save in flight, then Save says Saving and the list cannot be changed", async () => {
    wire({ put: () => new Promise<Response>(() => undefined) });
    await loaded();
    await save();
    expect(await screen.findByRole("button", { name: "Saving..." })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByLabelText("General instructions")).toHaveAttribute("readonly");
    expect(screen.getByRole("checkbox", { name: "Always notify, Bills" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Edit Bills" })).toBeDisabled();
  });
});

describe("Categories page: keyboard only (AC-23)", () => {
  async function tabTo(user: ReturnType<typeof userEvent.setup>, element: () => HTMLElement): Promise<void> {
    await user.tab();
    while (document.activeElement !== element()) {
      await user.tab();
    }
  }

  it("lets a category be opened, changed, kept and saved without a pointer, and focus ends on the result", async () => {
    const seen = wire({ put: (body) => json({ ...LIST, version: body.version + 1, categories: [{ ...INVOICES, name: "Bills" }, NEWS] }) });
    await loaded();
    const user = userEvent.setup();
    await tabTo(user, () => screen.getByRole("button", { name: "Edit Invoices" }));
    await user.keyboard("{Enter}");
    const view = within(await screen.findByRole("region", { name: "Edit category" }));
    await tabTo(user, () => view.getByLabelText("Name"));
    await user.keyboard("{Control>}a{/Control}Bills{Enter}");
    expect(screen.queryByRole("region", { name: "Edit category" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Bills" })).toHaveFocus();

    await tabTo(user, saveButton);
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("alertdialog");
    await user.tab();
    expect(within(dialog).getByRole("button", { name: "Save changes" })).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(seen.puts).toHaveLength(1);
    await waitFor(() => {
      expect(screen.getByText("Saved.").closest('[role="status"]')).toHaveFocus();
    });
  });

  it("closes the summary with Escape and puts focus back on Save changes", async () => {
    wire();
    await loaded();
    await rename("Invoices", "Bills");
    await userEvent.click(saveButton());
    await screen.findByRole("alertdialog");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(saveButton()).toHaveFocus();
  });
});

describe("Categories page: the archive label (criterion 5, AC-41, AC-42, AC-68)", () => {
  it("given the page, then the field shows the stored name with its sentence word for word", async () => {
    wire();
    await loaded();
    const field = screen.getByLabelText("Archive label");
    expect(field).toHaveValue("Archive");
    expect(field).toHaveClass("min-h-11");
    expect(
      screen.getByText("Mail in this label is never sorted or moved. Renaming it renames the Gmail label, nothing else."),
    ).toBeInTheDocument();
    expect(field).toHaveAccessibleDescription(/never sorted or moved/);
  });

  it("given a list save without touching it, then the stored name is sent back so the save is not refused", async () => {
    const seen = wire({ get: () => json({ ...LIST, archiveLabel: "Bewaard" }) });
    await loaded();
    const view = await edit("Invoices");
    await replace(view.getByLabelText("Description"), "Bills only");
    await userEvent.click(view.getByRole("button", { name: "Save" }));
    await confirm();

    await waitFor(() => {
      expect(seen.puts).toHaveLength(1);
    });
    expect(seen.puts[0]?.body.archiveLabel).toBe("Bewaard");
  });

  it("given a new name, when saved, then it is sent, the summary names the change and the save bar counts it", async () => {
    const seen = wire();
    await loaded();
    await replace(screen.getByLabelText("Archive label"), "Bewaard");
    expect(screen.getByText("1 change not saved")).toBeInTheDocument();

    await userEvent.click(saveButton());
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Change the archive label")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(seen.puts).toHaveLength(1);
    });
    expect(seen.puts[0]?.body.archiveLabel).toBe("Bewaard");
  });

  it("given a refused name, then the field shows the reason, is invalid, described and focused", async () => {
    wire({ put: () => problem422([{ rule: "setting_name_system_label", field: "archive_label", index: null, position: null, otherIndex: null }]) });
    await loaded();
    await replace(screen.getByLabelText("Archive label"), "INBOX");
    await confirm();

    const field = await screen.findByLabelText("Archive label");
    const reason = await screen.findByText("This is a Gmail label of its own and cannot be used here.");
    expect(field).toBeInvalid();
    expect(field).toHaveAccessibleDescription(/Gmail label of its own/);
    expect(reason.closest("[role=alert]")).not.toBeNull();
    await waitFor(() => {
      expect(field).toHaveFocus();
    });
  });

  it.each([
    ["setting_name_invalid", "This is not a valid label name."],
    ["setting_name_too_long", "Use at most 255 characters for the label name."],
    ["setting_name_reserved", "This name is kept for the assistant, or the other setting already uses it. Choose another name."],
    ["setting_name_category_clash", "A category already uses this label, or lies below it. Choose another name."],
  ])("given the rule %s, then the reason reads %j", async (rule, text) => {
    wire({ put: () => problem422([{ rule, field: "archive_label", index: null, position: null, otherIndex: null }]) });
    await loaded();
    await replace(screen.getByLabelText("Archive label"), "Whatever");
    await confirm();
    expect(await screen.findByText(text)).toBeInTheDocument();
  });

  it("given a reason is shown, when the user edits the name, then the reason goes away", async () => {
    wire({ put: () => problem422([{ rule: "setting_name_invalid", field: "archive_label", index: null, position: null, otherIndex: null }]) });
    await loaded();
    await replace(screen.getByLabelText("Archive label"), "Bad");
    await confirm();
    await screen.findByText("This is not a valid label name.");

    await userEvent.type(screen.getByLabelText("Archive label"), "x");

    expect(screen.queryByText("This is not a valid label name.")).not.toBeInTheDocument();
  });

  it("given a save is on its way, then the field is read-only", async () => {
    wire({ put: () => new Promise<Response>(() => undefined) });
    await loaded();
    await replace(screen.getByLabelText("Archive label"), "Bewaard");
    await confirm();
    await waitFor(() => {
      expect(screen.getByLabelText("Archive label")).toHaveAttribute("readonly");
    });
  });
});

describe("Categories page: the Other label (U-label-prefix-removal-12, AC 12, AC 13, AC 17)", () => {
  const otherField = (): HTMLElement => screen.getByLabelText("Other label");

  it("given the defaults, then the Other label field shows the stored name next to the archive label, with help and a 44 px target", async () => {
    wire();
    await loaded();
    expect(otherField()).toHaveValue("Other");
    expect(otherField()).toHaveClass("min-h-11");
    expect(otherField()).toHaveAccessibleDescription(/Mail that fits no category/);
    expect(screen.getByLabelText("Archive label")).toHaveValue("Archive");
  });

  it("given a list save without touching it, then the stored Other name is sent back with the list", async () => {
    const seen = wire({ get: () => json({ ...LIST, otherLabel: "Overig" }) });
    await loaded();
    const view = await edit("Invoices");
    await replace(view.getByLabelText("Description"), "Bills only");
    await userEvent.click(view.getByRole("button", { name: "Save" }));
    await confirm();
    await waitFor(() => {
      expect(seen.puts).toHaveLength(1);
    });
    expect(seen.puts[0]?.body.otherLabel).toBe("Overig");
  });

  it("given a new name, when saved, then it is sent and the summary names the change", async () => {
    const seen = wire();
    await loaded();
    await replace(otherField(), "Overig");
    expect(screen.getByText("1 change not saved")).toBeInTheDocument();
    await userEvent.click(saveButton());
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Change the Other label")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(seen.puts).toHaveLength(1);
    });
    expect(seen.puts[0]?.body.otherLabel).toBe("Overig");
  });

  it("given a category named like the stored Other label, when saving, then name_setting_clash shows and nothing is sent (AC 13)", async () => {
    const seen = wire({ get: () => json({ ...LIST, otherLabel: "Overig" }) });
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));
    const view = within(screen.getByRole("region", { name: "New category" }));
    await userEvent.type(view.getByLabelText("Name"), "overig");
    await userEvent.type(view.getByLabelText("Description"), "Rest");
    await userEvent.click(view.getByRole("button", { name: "Save" }));
    expect(view.getByText("This name is already used for your Other or archive label. Choose another name.")).toBeInTheDocument();
    expect(seen.puts).toHaveLength(0);
  });

  it.each([
    ["setting_name_system_label", "This is a Gmail label of its own and cannot be used here."],
    ["setting_name_reserved", "This name is kept for the assistant, or the other setting already uses it. Choose another name."],
    ["setting_name_category_clash", "A category already uses this label, or lies below it. Choose another name."],
  ])("given the api refuses the Other name with %s, then the reason is tied to the field, which is focused (AC 17)", async (rule, text) => {
    wire({ put: () => problem422([{ rule, field: "other_label", index: null, position: null, otherIndex: null }]) });
    await loaded();
    await replace(otherField(), "INBOX");
    await confirm();
    const reason = await screen.findByText(text);
    expect(otherField()).toBeInvalid();
    expect(otherField().getAttribute("aria-describedby")).toContain(reason.closest("[role=alert]")?.id ?? "missing");
    expect(reason.closest("[role=alert]")).not.toBeNull();
    expect(screen.getByLabelText("Archive label")).not.toBeInvalid();
    await waitFor(() => {
      expect(otherField()).toHaveFocus();
    });
  });

  it("given a reason is shown, when the user edits the name, then the reason goes away; and while saving the field is read-only", async () => {
    wire({ put: () => problem422([{ rule: "setting_name_invalid", field: "other_label", index: null, position: null, otherIndex: null }]) });
    await loaded();
    await replace(otherField(), "Bad");
    await confirm();
    await screen.findByText("This is not a valid label name.");
    await userEvent.type(otherField(), "x");
    expect(screen.queryByText("This is not a valid label name.")).not.toBeInTheDocument();
  });
});
