import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, vi } from "vitest";

import { setCsrfToken } from "@/api/client";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { expectNoAxeViolations } from "@/test/axe";

const DEFAULTS = {
  timeZone: "Europe/Amsterdam",
  quietStart: "23:00",
  quietEnd: "07:00",
  overviewAt: "18:00",
  remindAt: "09:00",
};
const CHANGED = { timeZone: "Asia/Bangkok", quietStart: "22:00", quietEnd: "06:30", overviewAt: "19:30", remindAt: "10:00" };
const STORED = { values: CHANGED, version: 1, updatedAt: "2026-11-12T10:00:00Z", updatedVia: "web" };
const TOKEN = "csrf-secret-4711";
const LISTED = "Time zone Europe/Amsterdam, quiet hours 23:00 to 07:00, daily overview 18:00, reminders 09:00";

type Answer = Response | Promise<Response>;

interface Posted {
  path: string;
  method: string;
  body: unknown;
  token: string | null;
}

interface Wire {
  posts: Posted[];
  puts: number;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const restoredAs = (version = 2): Response => json({ ...STORED, values: DEFAULTS, version, updatedVia: "web" });

/** GET answers the stored row; the reset POST goes to `reset`. */
function wire(reset: () => Answer = () => restoredAs()): Wire {
  const seen: Wire = { posts: [], puts: 0 };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const request = new Request(new URL(input, "http://localhost"), init);
      if (request.method === "PUT") {
        seen.puts += 1;
        return json(STORED);
      }
      if (request.method === "POST") {
        seen.posts.push({
          path: new URL(request.url).pathname,
          method: request.method,
          body: await request.json(),
          token: request.headers.get("X-CSRF-Token"),
        });
        return reset();
      }
      return json(STORED);
    }),
  );
  return seen;
}

function deferred(): { promise: Promise<Response>; resolve: (response: Response) => void } {
  let resolve: (response: Response) => void = () => undefined;
  const promise = new Promise<Response>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function loaded(): Promise<HTMLElement> {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const { container } = render(
    <QueryClientProvider client={client}>
      <SettingsPage />
    </QueryClientProvider>,
  );
  await screen.findByLabelText("Time zone");
  return container;
}

const resetButton = (): HTMLElement => screen.getByRole("button", { name: "Reset to defaults" });
const keepButton = (): HTMLElement => screen.getByRole("button", { name: "Keep my settings" });
const confirmButton = (): HTMLElement => screen.getByRole("button", { name: "Replace my settings with defaults" });
const save = (): HTMLElement => screen.getByRole("button", { name: /^(Save changes|Saving\.\.\.)$/ });

async function openDialog(): Promise<HTMLElement> {
  await userEvent.click(resetButton());
  return screen.getByRole("alertdialog");
}

async function typeOverview(value: string): Promise<void> {
  await userEvent.clear(screen.getByLabelText("Daily overview"));
  await userEvent.type(screen.getByLabelText("Daily overview"), value);
}

beforeEach(() => {
  setCsrfToken(TOKEN);
});

afterEach(() => {
  setCsrfToken(null);
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the confirmation (criterion 1)", () => {
  it("given the loaded page, when it is read, then Reset to defaults is a separate button after Save and the dialog is closed", async () => {
    wire();
    await loaded();

    expect(resetButton()).toBeEnabled();
    expect(save().compareDocumentPosition(resetButton()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.queryByText("Replace my settings with defaults")).not.toBeInTheDocument();
  });

  it("given the page is still loading, when it is read, then no Reset control is rendered yet", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => undefined)),
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    expect(screen.queryByRole("button", { name: /reset/i })).not.toBeInTheDocument();
  });

  it("given Reset is pressed, when the dialog opens, then it names the defaults and the time zone, and focus is on Keep my settings", async () => {
    const seen = wire();
    await loaded();

    const dialog = await openDialog();

    expect(dialog).toHaveAccessibleName("Reset to defaults?");
    expect(dialog).toHaveAccessibleDescription(expect.stringContaining(LISTED));
    expect(within(dialog).getByText(/The time zone is reset too\./)).toBeInTheDocument();
    expect(within(dialog).getByText(/It takes effect at once for new alerts\./)).toBeInTheDocument();
    expect(keepButton()).toHaveFocus();
    expect(seen.posts).toEqual([]);
  });

  it("given the open dialog, when axe runs, then there is no violation", async () => {
    wire();
    const container = await loaded();
    await openDialog();

    await expectNoAxeViolations(container);
  });
});

describe("leaving the dialog (criterion 2)", () => {
  it("given the dialog, when Escape is pressed, then it closes, nothing is sent and focus is back on Reset", async () => {
    const seen = wire();
    await loaded();
    await openDialog();

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(resetButton()).toHaveFocus();
    expect(seen.posts).toEqual([]);
  });

  it("given the dialog, when Keep my settings is pressed, then it closes, nothing is sent and focus is back on Reset", async () => {
    const seen = wire();
    await loaded();
    await openDialog();

    await userEvent.click(keepButton());

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(resetButton()).toHaveFocus();
    expect(seen.posts).toEqual([]);
    expect(screen.queryByText(/Defaults restored/)).not.toBeInTheDocument();
  });

  it("given a dialog that was closed, when Reset is pressed again, then it opens again with focus on Keep my settings", async () => {
    wire();
    await loaded();
    await openDialog();
    await userEvent.keyboard("{Escape}");

    await openDialog();

    expect(keepButton()).toHaveFocus();
  });
});

describe("keyboard containment (criterion 3)", () => {
  it("given the dialog is open, when Tab and Shift+Tab are pressed repeatedly, then focus never leaves it and it was opened as a modal", async () => {
    wire();
    await loaded();
    const showModal = vi.spyOn(HTMLDialogElement.prototype, "showModal");
    const dialog = await openDialog();

    for (let press = 0; press < 5; press += 1) {
      await userEvent.tab();
      expect(dialog).toContainElement(document.activeElement as HTMLElement);
    }
    for (let press = 0; press < 5; press += 1) {
      await userEvent.tab({ shift: true });
      expect(dialog).toContainElement(document.activeElement as HTMLElement);
    }
    expect(showModal).toHaveBeenCalledTimes(1);
  });

  it("given the dialog is open, when Tab leaves the last button, then focus comes back to the first one", async () => {
    wire();
    await loaded();
    await openDialog();

    await userEvent.tab();
    expect(confirmButton()).toHaveFocus();
    await userEvent.tab();
    expect(keepButton()).toHaveFocus();
  });
});

describe("confirming (criterion 4)", () => {
  it("given confirm, when pressed, then Save and Reset are disabled, one POST with the version goes out and the banner follows", async () => {
    const gate = deferred();
    const seen = wire(() => gate.promise);
    await loaded();
    await openDialog();

    await userEvent.click(confirmButton());

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(save()).toHaveAttribute("aria-disabled", "true");
    expect(resetButton()).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(resetButton());
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(seen.posts).toHaveLength(1);
    });
    expect(seen.posts[0]).toEqual({ path: "/api/settings/reset", method: "POST", body: { version: 1 }, token: TOKEN });

    gate.resolve(restoredAs());

    expect(await screen.findByText("Defaults restored.")).toBeInTheDocument();
    expect(screen.getByText(/The Undo button is in the Telegram message\./)).toBeInTheDocument();
    expect(seen.posts).toHaveLength(1);
    expect(seen.puts).toBe(0);
  });

  it("given the answer, when it arrives, then the fields show the defaults including the zone, Save is off and Reset is usable again", async () => {
    wire();
    await loaded();
    await openDialog();

    await userEvent.click(confirmButton());
    await screen.findByText("Defaults restored.");

    expect(screen.getByRole("combobox", { name: "Time zone" })).toHaveValue("Europe/Amsterdam");
    expect(screen.getByLabelText("From")).toHaveValue("23:00");
    expect(screen.getByLabelText("Until")).toHaveValue("07:00");
    expect(screen.getByLabelText("Daily overview")).toHaveValue("18:00");
    expect(screen.getByLabelText("Remind-me-later default")).toHaveValue("09:00");
    expect(save()).toBeDisabled();
    expect(resetButton()).not.toHaveAttribute("aria-disabled");
    expect(screen.queryByText("Could not save. Nothing was changed.")).not.toBeInTheDocument();
  });

  it("given typed edits and a kept draft, when the reset succeeds, then the draft is removed", async () => {
    wire();
    await loaded();
    await typeOverview("20:00");
    expect(window.sessionStorage.getItem("settings-draft")).not.toBeNull();
    await openDialog();

    await userEvent.click(confirmButton());
    await screen.findByText("Defaults restored.");

    expect(window.sessionStorage.getItem("settings-draft")).toBeNull();
    expect(screen.getByLabelText("Daily overview")).toHaveValue("18:00");
  });

  it("given the banner, when axe runs, then it is a polite status without violations", async () => {
    wire();
    const container = await loaded();
    await openDialog();
    await userEvent.click(confirmButton());

    const banner = (await screen.findByText("Defaults restored.")).closest("[role]");

    expect(banner).toHaveAttribute("role", "status");
    await expectNoAxeViolations(container);
  });
});

describe("a reset that did not happen (criterion 5)", () => {
  it("given a 409, when it arrives, then the conflict banner shows, nothing is replaced and there is no success banner", async () => {
    const current = { ...STORED, values: { ...CHANGED, quietStart: "21:00" }, version: 2, updatedVia: "telegram" };
    wire(() => json({ type: "x", title: "Conflict", status: 409, current }, 409));
    await loaded();
    await openDialog();

    await userEvent.click(confirmButton());

    expect(await screen.findByText(/Settings changed in Telegram/)).toBeInTheDocument();
    expect(screen.queryByText("Defaults restored.")).not.toBeInTheDocument();
    expect(screen.getByLabelText("From")).toHaveValue("21:00");
    expect(screen.getByRole("combobox", { name: "Time zone" })).toHaveValue("Asia/Bangkok");
    expect(resetButton()).not.toHaveAttribute("aria-disabled");
  });

  it("given a 409 and typed edits, when it arrives, then the edited field is offered as mine against the other side", async () => {
    const current = { ...STORED, values: { ...CHANGED, overviewAt: "21:00" }, version: 2, updatedVia: "telegram" };
    wire(() => json({ type: "x", title: "Conflict", status: 409, current }, 409));
    await loaded();
    await typeOverview("20:00");
    await openDialog();

    await userEvent.click(confirmButton());

    expect(await screen.findByText(/You typed 20:00, Telegram now has 21:00/)).toBeInTheDocument();
  });

  it("given a failed request, when it arrives, then a friendly error shows, the values stay and Reset can be tried again", async () => {
    wire(() => json({ title: "boom" }, 500));
    await loaded();
    await openDialog();

    await userEvent.click(confirmButton());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not reset. Nothing was changed.");
    expect(screen.queryByText("Defaults restored.")).not.toBeInTheDocument();
    expect(screen.getByLabelText("From")).toHaveValue("22:00");
    expect(resetButton()).not.toHaveAttribute("aria-disabled");
  });

  it("given a failed reset and a kept draft, when it fails, then the typed values stay in the draft", async () => {
    wire(() => json({ title: "boom" }, 500));
    await loaded();
    await typeOverview("20:00");
    await openDialog();

    await userEvent.click(confirmButton());
    await screen.findByRole("alert");

    expect(window.sessionStorage.getItem("settings-draft")).toContain("20:00");
  });
});
