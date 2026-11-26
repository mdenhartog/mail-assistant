import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RENAME_POLL_MS } from "@/api/categories/rename.queries";
import { expectNoAxeViolations } from "@/test/axe";
import { INVOICES, LIST, json, NO_RENAME, renderPage, wire } from "@/test/categories";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const HASH = "a".repeat(64);
const AMERIKA = { id: "id-amerika", oldName: "Assistant/Amerika", newName: "Amerika", mailCount: 40, action: "merge", itemState: "planned" };
const TRAVEL = { id: "id-travel", oldName: "Assistant/Travel", newName: "Travel", mailCount: 3, action: "rename", itemState: "planned" };
const BILLS = { id: "id-bills", oldName: "Assistant/Bills", newName: "Bills", mailCount: 12, action: "rename", itemState: "planned" };
const PENDING = { state: "pending", planHash: HASH, items: [TRAVEL, AMERIKA, BILLS], summary: { labels: 3, mails: 55 } };
const CONFIRMED = { ...PENDING, state: "confirmed" };
const DONE = {
  state: "done",
  planHash: HASH,
  items: [
    { ...AMERIKA, itemState: "done" },
    { ...BILLS, itemState: "skipped" },
    { ...TRAVEL, itemState: "done" },
  ],
  summary: { labels: 3, mails: 55 },
};

async function loaded(): Promise<HTMLElement> {
  const container = renderPage();
  await screen.findByRole("button", { name: `Edit ${INVOICES.name}` });
  return container;
}

async function loadedPending(options: Parameters<typeof wire>[0] = {}): Promise<ReturnType<typeof wire>> {
  const wired = wire({ rename: () => json(PENDING), ...options });
  await loaded();
  await screen.findByRole("group", { name: "Assistant/Amerika" });
  return wired;
}

async function loaded2(): Promise<HTMLElement> {
  wire({ rename: () => json(PENDING) });
  const container = await loaded();
  await screen.findByRole("group", { name: "Assistant/Amerika" });
  return container;
}

function cardNames(): string[] {
  const section = screen.getByRole("region", { name: "Rename your labels" });
  return within(section).getAllByRole("group").map((card) => card.getAttribute("aria-label") ?? "");
}

async function openConfirmation(): Promise<HTMLElement> {
  await userEvent.click(screen.getByRole("button", { name: "Rename these labels" }));
  return screen.findByRole("alertdialog");
}

async function confirmWith(text: string): Promise<void> {
  const dialog = await openConfirmation();
  await userEvent.type(within(dialog).getByRole("textbox"), text);
  await userEvent.click(within(dialog).getByRole("button", { name: "Rename labels" }));
}

describe("the rename preview (criterion 1, AC 4)", () => {
  it("given a pending plan, then the summary, the cards and a skip per label are shown, most mails first", async () => {
    await loadedPending();
    expect(screen.getByText("3 labels, 55 mails")).toBeInTheDocument();
    expect(cardNames()).toEqual(["Assistant/Amerika", "Assistant/Bills", "Assistant/Travel"]);
    const card = screen.getByRole("group", { name: "Assistant/Bills" });
    expect(within(card).getByText("Assistant/Bills")).toBeInTheDocument();
    expect(within(card).getByText("Bills")).toBeInTheDocument();
    expect(within(card).getByText("12 mails")).toBeInTheDocument();
    expect(within(card).getByRole("checkbox", { name: "Skip Assistant/Bills" })).not.toBeChecked();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("when the sort is changed, then the fewest mails come first", async () => {
    await loadedPending();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Sort by mail count" }), "Fewest mails first");
    expect(cardNames()).toEqual(["Assistant/Travel", "Assistant/Bills", "Assistant/Amerika"]);
  });

  it("given a label name with markup, then it is plain text, never markup or a link", async () => {
    const evil = { ...TRAVEL, oldName: 'Assistant/<a href="https://evil.example">x</a>', newName: "<b>y</b>" };
    wire({ rename: () => json({ ...PENDING, items: [evil] }) });
    await loaded();
    await screen.findAllByText('Assistant/<a href="https://evil.example">x</a>');
    expect(document.querySelector("a[href*='evil']")).toBeNull();
    expect(document.querySelector("b")).toBeNull();
  });

  it("given the plan is loading, then a status says so", async () => {
    wire({ rename: () => new Promise(() => undefined) });
    await loaded();
    expect(screen.getByText("Loading the rename preview")).toBeInTheDocument();
  });

  it("given the plan cannot be read, then it says so and Try again reads it again", async () => {
    let calls = 0;
    wire({
      rename: () => {
        calls += 1;
        return calls === 1 ? json({ detail: "x" }, 500) : json(PENDING);
      },
    });
    await loaded();
    await screen.findByText("Could not load the rename preview.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText("3 labels, 55 mails");
  });
});

describe("a merge item (criterion 2, AC 20)", () => {
  it("says merge N mails into an existing label", async () => {
    await loadedPending();
    const card = screen.getByRole("group", { name: "Assistant/Amerika" });
    expect(within(card).getByText("Merge 40 mails into an existing label")).toBeInTheDocument();
    const plain = screen.getByRole("group", { name: "Assistant/Travel" });
    expect(within(plain).queryByText(/existing label/)).not.toBeInTheDocument();
  });
});

describe("the typed confirmation (criterion 3)", () => {
  it("opens an alertdialog that explains what happens and sends nothing yet", async () => {
    const wired = await loadedPending();
    const dialog = await openConfirmation();
    expect(dialog).toHaveAccessibleName("Rename 3 labels?");
    expect(within(dialog).getByRole("textbox", { name: /Type 3 or RENAME/ })).toBeInTheDocument();
    expect(wired.confirmations).toEqual([]);
  });

  it("when the text does not match, then nothing is sent and the dialog says why", async () => {
    const wired = await loadedPending();
    await confirmWith("2");
    expect(wired.confirmations).toEqual([]);
    expect(within(screen.getByRole("alertdialog")).getByRole("alert")).toHaveTextContent("Type 3 or RENAME");
  });

  it("when Escape is pressed, then the dialog closes and nothing is sent", async () => {
    const wired = await loadedPending();
    await openConfirmation();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(wired.confirmations).toEqual([]);
  });

  it("when the word RENAME is typed with one label skipped, then the hash and the skipped id are sent once", async () => {
    let release: (response: Response) => void = () => undefined;
    const wired = await loadedPending({
      confirm: () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    });
    await userEvent.click(screen.getByRole("checkbox", { name: "Skip Assistant/Bills" }));
    const dialog = await openConfirmation();
    expect(dialog).toHaveAccessibleName("Rename 2 labels?");
    await userEvent.type(within(dialog).getByRole("textbox"), "RENAME");
    await userEvent.click(within(dialog).getByRole("button", { name: "Rename labels" }));
    const start = await screen.findByRole("button", { name: "Sending..." });
    expect(start).toHaveAttribute("aria-busy", "true");
    await userEvent.click(start);
    await userEvent.click(start);
    expect(wired.confirmations).toEqual([{ planHash: HASH, skippedIds: ["id-bills"] }]);
    act(() => {
      release(json({ confirmationId: "c" }, 201));
    });
  });

  it("when the number of labels is typed, then it is accepted", async () => {
    const wired = await loadedPending();
    await confirmWith("3");
    await waitFor(() => {
      expect(wired.confirmations).toEqual([{ planHash: HASH, skippedIds: [] }]);
    });
  });

  it("given every label is skipped, then the start button is disabled", async () => {
    await loadedPending();
    for (const name of ["Assistant/Amerika", "Assistant/Bills", "Assistant/Travel"]) {
      await userEvent.click(screen.getByRole("checkbox", { name: `Skip ${name}` }));
    }
    expect(screen.getByRole("button", { name: "Rename these labels" })).toBeDisabled();
  });

  it("given a label is skipped, then its card is not dimmed, so the muted text keeps its contrast", async () => {
    await loadedPending();
    await userEvent.click(screen.getByRole("checkbox", { name: "Skip Assistant/Bills" }));
    expect(screen.getByRole("group", { name: "Assistant/Bills" }).className).not.toMatch(/opacity/);
  });

  it("given the plan changed (409), then the preview is read again and a plain message says so", async () => {
    let reads = 0;
    const wired = wire({
      rename: () => {
        reads += 1;
        return json(reads === 1 ? PENDING : { ...PENDING, planHash: "b".repeat(64), items: [TRAVEL], summary: { labels: 1, mails: 3 } });
      },
      confirm: () => json({ detail: "x" }, 409),
    });
    await loaded();
    await screen.findByRole("group", { name: "Assistant/Amerika" });
    await confirmWith("RENAME");
    await screen.findByText(/The plan changed/);
    await screen.findByText("1 label, 3 mails");
    expect(wired.renameReads()).toBe(2);
  });

  it("given an unknown skipped id (422), then the preview is read again with a plain message", async () => {
    const wired = await loadedPending({ confirm: () => json({ detail: "x" }, 422) });
    await confirmWith("RENAME");
    await screen.findByText(/no longer in the plan/);
    await waitFor(() => {
      expect(wired.renameReads()).toBe(2);
    });
  });

  it("given another failure, then a friendly error shows and the plan stays", async () => {
    await loadedPending({ confirm: () => json({ detail: "x" }, 500) });
    await confirmWith("RENAME");
    await screen.findByText(/Could not start the rename/);
    expect(screen.getByRole("group", { name: "Assistant/Amerika" })).toBeInTheDocument();
  });
});

describe("an expired session (criterion 7)", () => {
  it("asks to sign in again and keeps the plan and the skipped label", async () => {
    await loadedPending({ confirm: () => json({ detail: "No session" }, 401) });
    await userEvent.click(screen.getByRole("checkbox", { name: "Skip Assistant/Bills" }));
    await confirmWith("RENAME");
    await screen.findByText(/Your session ended/);
    expect(screen.getByRole("link", { name: "Sign in again" })).toHaveAttribute("href", "/login?notice=expired");
    expect(screen.getByRole("checkbox", { name: "Skip Assistant/Bills" })).toBeChecked();
    expect(screen.getByRole("group", { name: "Assistant/Amerika" })).toBeInTheDocument();
  });
});

describe("renaming is in progress, then the result (criterion 4, AC 17, 27)", () => {
  it("given state confirmed, then a status says renaming is in progress", async () => {
    wire({ rename: () => json(CONFIRMED) });
    await loaded();
    expect(await screen.findByRole("status", { name: "Renaming is in progress" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rename these labels" })).not.toBeInTheDocument();
  });

  it("when the rename finishes, then the result, the notice and Restore show and focus moves to the result", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let reads = 0;
    wire({
      rename: () => {
        reads += 1;
        return json(reads === 1 ? CONFIRMED : DONE);
      },
    });
    await loaded();
    await screen.findByRole("status", { name: "Renaming is in progress" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RENAME_POLL_MS + 100);
    });
    const result = await screen.findByRole("region", { name: "Renaming finished" });
    expect(result).toHaveFocus();
    expect(within(result).getByText("2 of 3 labels renamed, 1 skipped")).toBeInTheDocument();
    expect(within(result).getByText("Gmail apps may show the old names for a while.")).toBeInTheDocument();
    expect(within(result).getByRole("button", { name: "Restore the old names" })).toBeInTheDocument();
  });

  it("given a finished rename on load, then the result shows without taking the focus", async () => {
    wire({ rename: () => json(DONE) });
    await loaded();
    const result = await screen.findByRole("region", { name: "Renaming finished" });
    expect(result).not.toHaveFocus();
  });

  it("when Restore is confirmed, then it is sent once as plain text and the focus moves to the result", async () => {
    const wired = wire({ rename: () => json(DONE) });
    await loaded();
    await userEvent.click(await screen.findByRole("button", { name: "Restore the old names" }));
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Restore names" }));
    const outcome = await screen.findByText(/The old names are being restored/);
    expect(wired.restores()).toBe(1);
    expect(outcome.closest("[tabindex='-1']")).toHaveFocus();
  });

  it("when Restore is answered with 409, then it says there is nothing to restore", async () => {
    wire({ rename: () => json(DONE), restore: () => json({ detail: "x" }, 409) });
    await loaded();
    await userEvent.click(await screen.findByRole("button", { name: "Restore the old names" }));
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Restore names" }));
    await screen.findByText(/Nothing to restore/);
  });

  it("when Restore is cancelled, then nothing is sent", async () => {
    const wired = wire({ rename: () => json(DONE) });
    await loaded();
    await userEvent.click(await screen.findByRole("button", { name: "Restore the old names" }));
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Keep the new names" }));
    expect(wired.restores()).toBe(0);
  });
});

describe("recently deleted (criterion 5, AC 29)", () => {
  const DELETED = {
    retentionDays: 30,
    items: [
      { name: "Assistant/Old", deletedAt: "2026-11-20T12:00:00Z" },
      { name: "Assistant/Newer", deletedAt: "2026-11-24T12:00:00Z" },
    ],
  };

  it("lists names and dates, newest first, with the retention stated, and nothing editable", async () => {
    wire({ deleted: () => json(DELETED) });
    await loaded();
    const section = await screen.findByRole("region", { name: "Recently deleted labels" });
    const items = await within(section).findAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining("Assistant/Newer"),
      expect.stringContaining("Assistant/Old"),
    ]);
    expect(within(items[0] as HTMLElement).getByText("24 Nov 2026")).toBeInTheDocument();
    expect(within(section).getByText(/30 days/)).toBeInTheDocument();
    expect(within(section).queryByRole("button")).not.toBeInTheDocument();
    expect(within(section).queryByRole("textbox")).not.toBeInTheDocument();
    expect(within(section).queryByRole("link")).not.toBeInTheDocument();
  });

  it("given nothing was deleted, then an empty message shows", async () => {
    wire();
    await loaded();
    const section = await screen.findByRole("region", { name: "Recently deleted labels" });
    await within(section).findByText("No label was deleted in the last 30 days.");
  });

  it("given the list cannot be read, then a friendly error with Try again shows", async () => {
    wire({ deleted: () => json({ detail: "x" }, 500) });
    await loaded();
    await screen.findByText("Could not load the recently deleted labels.");
  });
});

describe("the first-run empty state (criterion 6)", () => {
  it("given no categories and no rename, then it explains the YAML upload", async () => {
    wire({ get: () => json({ ...LIST, categories: [] }), rename: () => json(NO_RENAME) });
    renderPage();
    await screen.findByText("Load your YAML file first: the list is no longer read from Gmail.");
  });

  it("given a list and no rename, then nothing about renaming shows", async () => {
    wire();
    await loaded();
    await screen.findByRole("region", { name: "Recently deleted labels" });
    expect(screen.queryByText(/Load your YAML file first/)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Rename your labels" })).not.toBeInTheDocument();
  });
});

describe("accessibility (criterion 8, AC 17)", () => {
  it("has no axe violation in the preview and the dialog, and the tab order follows the page", async () => {
    const container = await loaded2();
    await expectNoAxeViolations(container);
    const headings = screen.getAllByRole("heading").map((heading) => heading.tagName);
    expect(headings.slice(0, 2)).toEqual(["H1", "H2"]);
    const dialog = await openConfirmation();
    await expectNoAxeViolations(container);
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    await userEvent.tab();
    expect(within(dialog).getByRole("button", { name: "Rename labels" })).toHaveFocus();
    await userEvent.tab();
    expect(within(dialog).getByRole("textbox")).toHaveFocus();
  });

  it("has no axe violation in the result with Restore", async () => {
    wire({ rename: () => json(DONE), deleted: () => json({ retentionDays: 30, items: [{ name: "Assistant/Old", deletedAt: "2026-11-20T12:00:00Z" }] }) });
    const container = await loaded();
    await screen.findByRole("region", { name: "Renaming finished" });
    await screen.findByText("Assistant/Old");
    await expectNoAxeViolations(container);
  });
});
