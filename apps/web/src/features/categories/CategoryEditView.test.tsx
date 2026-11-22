import { screen, within } from "@testing-library/react";
import type { BoundFunctions, queries } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { expectNoAxeViolations } from "@/test/axe";
import { INVOICES, LIST, NEWS, json, renderPage, wire } from "@/test/categories";

type View = BoundFunctions<typeof queries>;

afterEach(() => {
  vi.unstubAllGlobals();
});

const HOME = {
  ...NEWS,
  id: "7f0c1c2e-1b1e-4c52-9d0e-0a6a1b1c0003",
  name: "Huis/Energie",
  senders: [{ entry: "x.nl", subdomains: true, skippedCount: 0 }],
};

async function openEdit(name: string): Promise<View> {
  await userEvent.click(await screen.findByRole("button", { name: `Edit ${name}` }));
  return within(screen.getByRole("region", { name: "Edit category" }));
}

async function open(name: string, categories = [INVOICES, NEWS]): Promise<View> {
  wire({ get: () => json({ ...LIST, categories }) });
  renderPage();
  const search = await screen.findByRole("searchbox", { name: "Search categories" });
  await userEvent.type(search, name);
  const view = await openEdit(name);
  return view;
}

describe("the sender textarea (criterion 3, AC-65)", () => {
  it("shows one entry per line, with the subdomains marker, and a live count", async () => {
    const view = await open("Huis/Energie", [INVOICES, { ...HOME, name: "Huis/Energie" }]);
    expect(view.getByLabelText("Senders")).toHaveValue("x.nl +subdomains");
    expect(view.getByText("1 of 100")).toBeInTheDocument();

    const field = view.getByLabelText("Senders");
    await userEvent.clear(field);
    await userEvent.type(field, "a@y.nl{Enter}b@y.nl{Enter}{Enter}c@y.nl");
    expect(view.getByText("3 of 100")).toBeInTheDocument();
    expect(field).toHaveAccessibleDescription(/3 of 100/);
  });

  it("names the other category of the same kind that already lists the entry, on that line, while typing", async () => {
    const view = await open("Newsletters", [{ ...HOME, kind: "topic" }, NEWS]);
    const field = view.getByLabelText("Senders");
    await userEvent.type(field, "ok@z.nl{Enter}X.NL");

    expect(field).toBeInvalid();
    const error = view.getByText("Line 2: X.NL is already in Huis/Energie. Remove it there first.");
    expect(field).toHaveAccessibleDescription(expect.stringContaining("Line 2: X.NL is already in Huis/Energie."));
    expect(error).toBeInTheDocument();
    expect(view.getByText("Remove it there first.", { exact: false })).toBeInTheDocument();
  });

  it("does not call it a conflict when the other category is of the other kind", async () => {
    const view = await open("Invoices", [INVOICES, { ...HOME, kind: "topic", senders: [{ entry: "billing@example.com", subdomains: false, skippedCount: 0 }] }]);
    expect(view.getByLabelText("Senders")).not.toBeInvalid();
  });

  it("shows more than 100 lines as an error with the count over the limit", async () => {
    const view = await open("Newsletters");
    const field = view.getByLabelText("Senders");
    await userEvent.click(field);
    await userEvent.paste(Array.from({ length: 101 }, (_, index) => `s${String(index)}@x.nl`).join("\n"));

    expect(view.getByText("101 of 100")).toBeInTheDocument();
    expect(view.getByText("A category can list at most 100 senders.")).toBeInTheDocument();
    expect(field).toBeInvalid();
  });

  it("refuses Save while the senders have an error and moves focus to the textarea", async () => {
    const view = await open("Newsletters", [{ ...HOME, kind: "topic" }, NEWS]);
    await userEvent.type(view.getByLabelText("Senders"), "x.nl");
    await userEvent.click(view.getByRole("button", { name: "Save" }));

    expect(screen.getByRole("region", { name: "Edit category" })).toBeInTheDocument();
    expect(view.getByLabelText("Senders")).toHaveFocus();
  });

  it("has no axe violations with a sender error", async () => {
    const view = await open("Newsletters", [{ ...HOME, kind: "topic" }, NEWS]);
    await userEvent.type(view.getByLabelText("Senders"), "x.nl");
    await expectNoAxeViolations(document.body.firstElementChild as Element);
  });
});

describe("the other fields of the edit view", () => {
  it("changes the kind with the radio buttons and shows the tick with its alert note", async () => {
    const view = await open("Newsletters");
    expect(view.getByRole("radio", { name: "Topic" })).toBeChecked();
    await userEvent.click(view.getByRole("radio", { name: "Extra label" }));
    expect(view.getByRole("radio", { name: "Extra label" })).toBeChecked();
    expect(view.getByRole("radio", { name: "Topic" })).not.toBeChecked();
    expect(view.getByText(/Alerts are limited per hour/)).toBeInTheDocument();
  });

  it("shows an empty name and description with their reasons and keeps the view open", async () => {
    const view = await open("Newsletters");
    await userEvent.clear(view.getByLabelText("Name"));
    await userEvent.clear(view.getByLabelText("Description"));
    await userEvent.click(view.getByRole("button", { name: "Save" }));

    const name = view.getByLabelText("Name");
    expect(name).toBeInvalid();
    expect(name).toHaveFocus();
    expect(name).toHaveAccessibleDescription(expect.stringContaining("Give the category a name."));
    expect(view.getByText("Say what belongs in this category.")).toBeInTheDocument();
  });

  it("deletes the category from the edit view with a notice and Undo on the list", async () => {
    const view = await open("Newsletters");
    await userEvent.click(view.getByRole("button", { name: "Delete Newsletters" }));

    expect(screen.queryByRole("region", { name: "Edit category" })).not.toBeInTheDocument();
    expect(screen.getByText("Removed Newsletters.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(await screen.findByRole("button", { name: "Edit Newsletters" })).toHaveFocus();
  });
});

describe("the skipped count beside a sender entry (U-label-structure-38)", () => {
  const SKIPPED = [
    { entry: "a@x.nl", subdomains: false, skippedCount: 3 },
    { entry: "b.nl", subdomains: true, skippedCount: 1 },
    { entry: "c@x.nl", subdomains: false, skippedCount: 0 },
  ];

  it("shows the count of an entry as text that the field's description carries, and the note", async () => {
    const view = await open("Newsletters", [INVOICES, { ...NEWS, senders: SKIPPED }]);
    const field = view.getByLabelText("Senders");

    expect(view.getByText("Not applied 3 times: Gmail could not confirm the sender")).toBeInTheDocument();
    expect(view.getByText("Not applied 1 time: Gmail could not confirm the sender")).toBeInTheDocument();
    expect(view.getAllByText(/Not applied/)).toHaveLength(2);
    expect(view.getByText("The AI judged those mails instead.")).toBeInTheDocument();
    expect(field).toHaveAccessibleDescription(expect.stringContaining("Not applied 3 times: Gmail could not confirm the sender"));
    expect(field).toHaveAccessibleDescription(expect.stringContaining("The AI judged those mails instead."));
    await expectNoAxeViolations(screen.getByRole("region", { name: "Edit category" }));
  });

  it("names the entry the count belongs to", async () => {
    const view = await open("Newsletters", [INVOICES, { ...NEWS, senders: SKIPPED }]);
    const item = view.getByText("Not applied 3 times: Gmail could not confirm the sender").closest("li");
    expect(item).toHaveTextContent("a@x.nl");
  });

  it("shows no line and no note when every count is 0", async () => {
    const view = await open("Invoices");
    expect(view.queryByText(/Not applied/)).not.toBeInTheDocument();
    expect(view.queryByText("The AI judged those mails instead.")).not.toBeInTheDocument();
  });

  it("shows no line for an entry the user edited or added", async () => {
    const view = await open("Newsletters", [INVOICES, { ...NEWS, senders: SKIPPED }]);
    const field = view.getByLabelText("Senders");
    await userEvent.clear(field);
    await userEvent.type(field, "new@x.nl{Enter}B.NL +subdomains");

    expect(view.getAllByText(/Not applied/)).toHaveLength(1);
    expect(view.getByText("Not applied 1 time: Gmail could not confirm the sender")).toBeInTheDocument();
    await userEvent.clear(field);
    await userEvent.type(field, "other@x.nl");
    expect(view.queryByText(/Not applied/)).not.toBeInTheDocument();
    expect(view.queryByText("The AI judged those mails instead.")).not.toBeInTheDocument();
  });

  it("renders an entry that looks like markup as inert text", async () => {
    const view = await open("Newsletters", [INVOICES, { ...NEWS, senders: [{ entry: "<b>x</b>@x.nl", subdomains: false, skippedCount: 2 }] }]);
    expect(view.getByText("<b>x</b>@x.nl", { selector: "span" })).toBeInTheDocument();
    expect(view.queryByRole("strong")).not.toBeInTheDocument();
  });
});
