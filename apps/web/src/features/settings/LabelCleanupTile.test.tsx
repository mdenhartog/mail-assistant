import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setCsrfToken } from "@/api/client";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { expectNoAxeViolations } from "@/test/axe";

const VALUES = {
  timeZone: "Europe/Amsterdam",
  quietStart: "23:00",
  quietEnd: "07:00",
  overviewAt: "18:00",
  remindAt: "09:00",
  waitingMinutes: 720,
  protectionDays: 7,
  retentionDays: 30,
};
/** Ranges as the api sends them; the protection maximum differs from the spec so a copy in the page would show. */
const RANGES = {
  waitingMinutes: { min: 5, max: 720, default: 720 },
  protectionDays: { min: 1, max: 30, default: 7 },
  retentionDays: { min: 7, max: 90, default: 30 },
};
const STORED = { values: VALUES, ranges: RANGES, version: 3, updatedAt: "2026-11-12T13:02:00Z", updatedVia: "telegram" };
const TOKEN = "csrf-secret-4711";

type Values = typeof VALUES;
interface Put {
  body: { values: Values; version: number };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function wire(options: { get?: () => Response; put?: (body: Put["body"]) => Response } = {}): Put[] {
  const puts: Put[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const request = new Request(new URL(input, "http://localhost"), init);
      if (request.method === "GET") {
        return options.get ? options.get() : json(STORED);
      }
      const body = (await request.json()) as Put["body"];
      puts.push({ body });
      return options.put ? options.put(body) : json({ ...STORED, values: body.values, version: body.version + 1 });
    }),
  );
  return puts;
}

function renderPage(): HTMLElement {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SettingsPage />
    </QueryClientProvider>,
  ).container;
}

async function loaded(): Promise<HTMLElement> {
  const container = renderPage();
  await screen.findByRole("region", { name: "Label cleanup" });
  return container;
}

function type(label: string, value: string): void {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

const save = (): HTMLElement => screen.getByRole("button", { name: /^(Save changes|Saving\.\.\.)$/ });

beforeEach(() => {
  setCsrfToken(TOKEN);
  window.sessionStorage.clear();
});

afterEach(() => {
  setCsrfToken(null);
  vi.unstubAllGlobals();
});

describe("the Label cleanup tile (criterion 1)", () => {
  it("given the defaults, when the page loads, then the tile shows each value, its range and its default as help text", async () => {
    wire();
    await loaded();
    const tile = within(screen.getByRole("region", { name: "Label cleanup" }));

    expect(tile.getByRole("heading", { level: 2, name: "Label cleanup" })).toBeInTheDocument();
    const waiting = within(tile.getByRole("group", { name: "Waiting time before a delete" }));
    expect(waiting.getByLabelText("Hours")).toHaveValue(12);
    expect(waiting.getByLabelText("Minutes")).toHaveValue(0);
    expect(waiting.getByLabelText("Hours")).toHaveAccessibleDescription(/5 minutes to 12 hours, default 12 hours/);
    expect(waiting.getByLabelText("Minutes")).toHaveAccessibleDescription(/5 minutes to 12 hours, default 12 hours/);
    expect(tile.getByLabelText("Protection period (days)")).toHaveValue(7);
    expect(tile.getByLabelText("Protection period (days)")).toHaveAccessibleDescription(/1 to 30 days, default 7 days/);
    expect(tile.getByLabelText("Retention (days)")).toHaveValue(30);
    expect(tile.getByLabelText("Retention (days)")).toHaveAccessibleDescription(/7 to 90 days, default 30 days/);
  });

  it("given other ranges from the api, then the help text shows those, not a copy of the page", async () => {
    wire({ get: () => json({ ...STORED, ranges: { ...RANGES, protectionDays: { min: 2, max: 14, default: 5 } } }) });
    await loaded();
    expect(screen.getByLabelText("Protection period (days)")).toHaveAccessibleDescription(/2 to 14 days, default 5 days/);
  });

  it("given a stored waiting time of 150 minutes, then it is shown as 2 hours and 30 minutes", async () => {
    wire({ get: () => json({ ...STORED, values: { ...VALUES, waitingMinutes: 150 } }) });
    await loaded();
    expect(screen.getByLabelText("Hours")).toHaveValue(2);
    expect(screen.getByLabelText("Minutes")).toHaveValue(30);
  });

  it("given values typed in the tile, when saved, then the three numbers go with the form on the stored version", async () => {
    const puts = wire();
    await loaded();
    type("Hours", "2");
    type("Minutes", "30");
    type("Protection period (days)", "14");
    type("Retention (days)", "60");
    await userEvent.click(save());

    await waitFor(() => {
      expect(puts).toHaveLength(1);
    });
    expect(puts[0]?.body).toEqual({ values: { ...VALUES, waitingMinutes: 150, protectionDays: 14, retentionDays: 60 }, version: 3 });
    expect(await screen.findByText(/^Saved/)).toBeInTheDocument();
  });
});

describe("a value outside its range (criterion 2, AC 33)", () => {
  it.each([
    ["Protection period (days)", "31", /1 to 30 days/],
    ["Protection period (days)", "0", /1 to 30 days/],
    ["Retention (days)", "6", /7 to 90 days/],
    ["Retention (days)", "91", /7 to 90 days/],
  ])("given %s typed as %s, when saved, then an inline message is tied to the field, focus goes to it and nothing is sent", async (label, value, message) => {
    const puts = wire();
    await loaded();
    type(label, value);
    await userEvent.click(save());

    const field = screen.getByLabelText(label);
    expect(field).toBeInvalid();
    expect(field).toHaveAccessibleDescription(message);
    expect(screen.getByRole("alert")).toHaveTextContent(message);
    expect(field).toHaveFocus();
    expect(puts).toHaveLength(0);
  });

  it("given a field that is emptied, when saved, then it asks for a number and nothing is sent", async () => {
    const puts = wire();
    await loaded();
    type("Retention (days)", "");
    await userEvent.click(save());

    expect(screen.getByLabelText("Retention (days)")).toBeInvalid();
    expect(screen.getByRole("alert")).toHaveTextContent(/7 to 90 days/);
    expect(puts).toHaveLength(0);
  });

  it("given a message is shown, when the user edits the field, then the message goes away", async () => {
    wire();
    await loaded();
    type("Protection period (days)", "40");
    await userEvent.click(save());
    expect(screen.getByLabelText("Protection period (days)")).toBeInvalid();
    type("Protection period (days)", "4");
    expect(screen.getByLabelText("Protection period (days)")).toBeValid();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("given the api refuses a number (422), then its rule shows as plain words at the field", async () => {
    wire({
      put: () =>
        json(
          {
            type: "about:blank",
            title: "Unprocessable",
            status: 422,
            problems: [{ field: "protectionDays", rule: "protection_days_out_of_range", value: "31", example: "7" }],
          },
          422,
        ),
    });
    await loaded();
    type("Protection period (days)", "12");
    await userEvent.click(save());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The protection period can be 1 to 30 days. The default is 7 days.");
    expect(alert.textContent).not.toContain("protection_days_out_of_range");
    expect(screen.getByLabelText("Protection period (days)")).toBeInvalid();
  });
});

describe("the waiting time as hours and minutes (criterion 3)", () => {
  it.each([
    ["12", "0", 720],
    ["0", "5", 5],
    ["1", "75", 135],
  ])("given %s hours and %s minutes, when saved, then %i minutes are sent", async (hours, minutes, total) => {
    const puts = wire({ get: () => json({ ...STORED, values: { ...VALUES, waitingMinutes: 60 } }) });
    await loaded();
    type("Hours", hours);
    type("Minutes", minutes);
    await userEvent.click(save());
    await waitFor(() => {
      expect(puts).toHaveLength(1);
    });
    expect(puts[0]?.body.values.waitingMinutes).toBe(total);
  });

  it.each([
    ["12", "1"],
    ["13", "0"],
    ["0", "4"],
    ["0", "0"],
  ])("given %s hours and %s minutes, when saved, then the group shows the range and nothing is sent", async (hours, minutes) => {
    const puts = wire({ get: () => json({ ...STORED, values: { ...VALUES, waitingMinutes: 60 } }) });
    await loaded();
    type("Hours", hours);
    type("Minutes", minutes);
    await userEvent.click(save());

    expect(screen.getByRole("group", { name: "Waiting time before a delete" })).toBeInTheDocument();
    expect(screen.getByLabelText("Hours")).toBeInvalid();
    expect(screen.getByLabelText("Minutes")).toBeInvalid();
    expect(screen.getByLabelText("Hours")).toHaveAccessibleDescription(/5 minutes to 12 hours/);
    expect(screen.getByLabelText("Minutes")).toHaveAccessibleDescription(/5 minutes to 12 hours/);
    expect(screen.getByRole("alert")).toHaveTextContent("The waiting time can be 5 minutes to 12 hours. The default is 12 hours.");
    expect(screen.getByLabelText("Hours")).toHaveFocus();
    expect(puts).toHaveLength(0);
  });
});

describe("states and the rest of the form (criterion 4)", () => {
  it("given the settings are loading, then the skeleton is shown and no tile yet", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
    renderPage();
    expect(screen.getByText("Loading your settings").closest("[aria-busy='true']")).not.toBeNull();
    expect(screen.queryByRole("region", { name: "Label cleanup" })).not.toBeInTheDocument();
  });

  it("given the settings cannot be read, then a danger banner offers Try again and the tile comes back with it", async () => {
    let answers = 0;
    wire({ get: () => (answers++ === 0 ? new Response(null, { status: 500 }) : json(STORED)) });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load your settings.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("region", { name: "Label cleanup" })).toBeInTheDocument();
  });

  it("given an answer without the ranges, then the page says it could not load", async () => {
    wire({ get: () => json({ ...STORED, ranges: undefined }) });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load your settings.");
  });

  it("given a change in the tile only, then Save changes is enabled, and typing the stored value again disables it", async () => {
    wire();
    await loaded();
    expect(save()).toBeDisabled();
    type("Retention (days)", "31");
    expect(save()).toBeEnabled();
    type("Retention (days)", "30");
    expect(save()).toBeDisabled();
  });

  it("given a value typed and the page opened again in the same tab, then the typed numbers come back as a draft", async () => {
    wire();
    await loaded();
    type("Protection period (days)", "9");
    cleanup();
    renderPage();
    await screen.findByRole("region", { name: "Label cleanup" });
    expect(screen.getByLabelText("Protection period (days)")).toHaveValue(9);
  });

  it("given another change to a number was stored meanwhile (409), then the conflict names the field in words", async () => {
    let first = true;
    wire({
      put: () => {
        if (first) {
          first = false;
          return json({ detail: "conflict", current: { ...STORED, values: { ...VALUES, protectionDays: 20 }, version: 4, updatedVia: "web" } }, 409);
        }
        return json(STORED);
      },
    });
    await loaded();
    type("Protection period (days)", "9");
    await userEvent.click(save());

    expect(await screen.findByText("You typed 9 days, the web now has 20 days")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use mine for Protection period" })).toBeInTheDocument();
  });
});

describe("keyboard, screen reader and small screens (criteria 5 and 6, AC 17)", () => {
  it("given the tile, then every control has a name, a 44 px target and nothing forces a width", async () => {
    wire();
    const container = await loaded();
    const tile = screen.getByRole("region", { name: "Label cleanup" });
    const controls = within(tile).getAllByRole("spinbutton");

    expect(controls.map((control) => control.getAttribute("id"))).not.toContain(null);
    expect(within(tile).getAllByRole("spinbutton").map((control) => (control as HTMLInputElement).labels?.[0]?.textContent)).toEqual([
      "Hours",
      "Minutes",
      "Protection period (days)",
      "Retention (days)",
    ]);
    for (const control of controls) {
      expect(control).toHaveClass("min-h-11", "max-w-full", "min-w-0");
      expect(control).toHaveAttribute("inputmode", "numeric");
    }
    const arbitrary = Array.from(container.querySelectorAll("*")).filter((node) =>
      (node.getAttribute("class") ?? "").includes("["),
    );
    expect(arbitrary).toEqual([]);
    await expectNoAxeViolations(container);
  });

  it("given the keyboard only, when Save is pressed with a wrong number, then focus is on the first wrong control with its message read", async () => {
    wire();
    await loaded();
    type("Retention (days)", "2");
    screen.getByLabelText("Retention (days)").focus();
    await userEvent.keyboard("{Enter}");

    await waitFor(() => {
      expect(screen.getByLabelText("Retention (days)")).toHaveFocus();
    });
    expect(screen.getByLabelText("Retention (days)")).toHaveAccessibleDescription(/7 to 90 days/);
  });

  it("given a saved change, then the result is announced in the existing status line", async () => {
    wire();
    await loaded();
    type("Protection period (days)", "8");
    await userEvent.click(save());
    expect((await screen.findByText(/^Saved/)).closest("[role=status]")).not.toBeNull();
  });
});
