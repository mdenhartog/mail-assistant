import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, vi } from "vitest";

import { setCsrfToken } from "@/api/client";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { expectNoAxeViolations } from "@/test/axe";
import { expectMotionOnlyWhenSafe } from "@/test/motion";

const VALUES = {
  timeZone: "Europe/Amsterdam",
  quietStart: "23:00",
  quietEnd: "07:00",
  overviewAt: "18:00",
  remindAt: "09:00",
};
const STORED = { values: VALUES, version: 3, updatedAt: "2026-11-12T13:02:00Z", updatedVia: "telegram" };
const HINTS = {
  zone: "The times below are local times in this zone.",
  overview: "When I send you the summary of your mail.",
  remind: "When a snoozed alert comes back if you do not name a time.",
};
const TOKEN = "csrf-secret-4711";
const MARKUP = "<img src=x onerror=alert(1)>";

type Answer = Response | Promise<Response>;
type Handler = () => Answer;
type Sent = { values: typeof VALUES; version: number };

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function problems(...items: [field: string, rule: string, value: string, example: string][]): Response {
  return json(
    {
      type: "about:blank",
      title: "Unprocessable",
      status: 422,
      problems: items.map(([field, rule, value, example]) => ({ field, rule, value, example })),
    },
    422,
  );
}

function savedAs(values: typeof VALUES, version = 4): Response {
  return json({ ...STORED, values, version });
}

interface Wire {
  puts: { body: Sent; token: string | null }[];
}

/** GET answers `get`; PUT goes to `put` (default: echo the values at the next version). */
function wire(put?: Handler, get: Handler = () => json(STORED)): Wire {
  const seen: Wire = { puts: [] };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const request = new Request(new URL(input, "http://localhost"), init);
      if (request.method === "GET") {
        return get();
      }
      const body = (await request.json()) as Sent;
      seen.puts.push({ body, token: request.headers.get("X-CSRF-Token") });
      return put ? put() : savedAs(body.values);
    }),
  );
  return seen;
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
  await screen.findByLabelText("Time zone");
  return container;
}

function setTime(label: string, value: string): void {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

const save = (): HTMLElement => screen.getByRole("button", { name: /^(Save changes|Saving\.\.\.)$/ });

function deferred(): { promise: Promise<Response>; resolve: (response: Response) => void } {
  let resolve: (response: Response) => void = () => undefined;
  const promise = new Promise<Response>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

beforeEach(() => {
  setCsrfToken(TOKEN);
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  setCsrfToken(null);
  vi.unstubAllGlobals();
});

describe("loading (criterion 1)", () => {
  it("given the settings are on their way, when rendered, then skeleton rows, the text, aria-busy and no Save button", async () => {
    wire(undefined, () => new Promise<Response>(() => undefined));

    const container = renderPage();

    expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
    expect(screen.getByText("Loading your settings").closest("[aria-busy='true']")).not.toBeNull();
    const rows = container.querySelectorAll("[data-skeleton]");
    expect(rows.length).toBeGreaterThanOrEqual(3);
    rows.forEach((row) => {
      expectMotionOnlyWhenSafe(row);
    });
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
    await expectNoAxeViolations(container);
  });

  it("given the settings cannot be read, when rendered, then a danger banner offers Try again and it works", async () => {
    let answers = 0;
    wire(undefined, () => (answers++ === 0 ? new Response(null, { status: 500 }) : json(STORED)));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load your settings.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByLabelText("Time zone")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("given an answer that is not settings, when rendered, then the same banner is shown", async () => {
    wire(undefined, () => json({ nonsense: true }));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load your settings.");
  });
});

describe("loaded (criteria 2 and 3)", () => {
  beforeEach(() => {
    wire();
  });

  it("given loaded settings, when rendered, then the four fields come in order with their values and hints", async () => {
    const container = await loaded();

    const zone = screen.getByLabelText("Time zone");
    const quiet = screen.getByRole("group", { name: "Quiet hours" });
    const overview = screen.getByLabelText("Daily overview");
    const remind = screen.getByLabelText("Remind-me-later default");
    const order = [zone, quiet, overview, remind];
    order.slice(1).forEach((element, index) => {
      expect(order[index]?.compareDocumentPosition(element)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    });
    expect(screen.getByLabelText("From")).toHaveValue("23:00");
    expect(screen.getByLabelText("Until")).toHaveValue("07:00");
    expect(overview).toHaveValue("18:00");
    expect(remind).toHaveValue("09:00");
    expect(zone).toHaveAccessibleDescription(HINTS.zone);
    expect(overview).toHaveAccessibleDescription(HINTS.overview);
    expect(remind).toHaveAccessibleDescription(HINTS.remind);
    expect(screen.getByLabelText("From")).toHaveAccessibleDescription(/\S/);
    expect(screen.getByLabelText("Until")).toHaveAccessibleDescription(/\S/);
    await expectNoAxeViolations(container);
  });

  it("given a narrow window or large text, when the cards are laid out, then one shrinkable column holds them (AC-22, U-36 finding)", async () => {
    await loaded();

    const grid = screen.getByLabelText("Time zone").closest(".grid");
    expect(grid).toHaveClass("grid-cols-1", "sm:grid-cols-2");
  });

  it("given the time fields are wider than a narrow card, when laid out, then they may shrink instead of pushing the page wide (AC-22, U-36 finding)", async () => {
    await loaded();

    const from = screen.getByLabelText("From");
    expect(from).toHaveClass("max-w-full");
    expect(from.parentElement).toHaveClass("min-w-0", "max-w-full");
    expect(from.parentElement?.parentElement).toHaveClass("min-w-0", "max-w-full");
  });

  it("given nothing changed, when viewed, then Save is disabled; after an edit it is enabled; undoing the edit disables it again", async () => {
    await loaded();
    expect(save()).toBeDisabled();

    setTime("Daily overview", "19:30");
    expect(save()).toBeEnabled();

    setTime("Daily overview", "18:00");
    expect(save()).toBeDisabled();
  });

  it("given settings, when loaded and edited, then nothing is written to localStorage and only the draft to sessionStorage", async () => {
    await loaded();
    setTime("Daily overview", "19:30");

    expect(window.localStorage).toHaveLength(0);
    expect(Object.keys(window.sessionStorage)).toEqual(["settings-draft"]);
    expect(window.sessionStorage.getItem("settings-draft")).not.toContain(TOKEN);
  });

  it("given the R1 build, when the page is searched, then there is no Reset control", async () => {
    await loaded();

    expect(screen.queryByRole("button", { name: /reset/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/reset/i)).not.toBeInTheDocument();
  });
});

describe("saving (criterion 4)", () => {
  it("given Save pressed several times, when the request runs, then label, aria-disabled, read-only inputs, status and exactly one PUT", async () => {
    const gate = deferred();
    const seen = wire(() => gate.promise);
    const container = await loaded();
    setTime("Daily overview", "19:30");

    await userEvent.click(save());
    await userEvent.click(save());
    await userEvent.dblClick(save());

    const button = await screen.findByRole("button", { name: "Saving..." });
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).not.toBeDisabled();
    expect(screen.getByLabelText("Time zone")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Daily overview")).toHaveAttribute("readonly");
    expect(screen.getByText("Saving your settings.")).toHaveAttribute("role", "status");
    expect(seen.puts).toHaveLength(1);
    expect(seen.puts[0]?.token).toBe(TOKEN);
    expect(seen.puts[0]?.body).toEqual({ values: { ...VALUES, overviewAt: "19:30" }, version: 3 });
    await expectNoAxeViolations(container);

    gate.resolve(savedAs({ ...VALUES, overviewAt: "19:30" }));
    await waitFor(() => {
      expect(screen.queryByText("Saving your settings.")).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(screen.getByLabelText("Daily overview")).not.toHaveAttribute("readonly");
    expect(screen.getByLabelText("Daily overview")).toHaveValue("19:30");
  });

  it("given a saved change, when edited again and saved, then the second PUT is based on the new version", async () => {
    const seen = wire();
    await loaded();
    setTime("Daily overview", "19:30");
    await userEvent.click(save());
    await waitFor(() => {
      expect(save()).toBeDisabled();
    });

    setTime("Remind-me-later default", "10:00");
    await userEvent.click(save());

    await waitFor(() => {
      expect(seen.puts).toHaveLength(2);
    });
    expect(seen.puts[1]?.body.version).toBe(4);
  });
});

describe("validation error (criterion 5)", () => {
  async function refusedWithTwoProblems(): Promise<HTMLElement> {
    wire(() =>
      problems(
        ["overviewAt", "overview_in_quiet_hours", "23:30", "Try 07:00"],
        ["remindAt", "remind_in_quiet_hours", "23:15", "Try 07:00"],
      ),
    );
    const container = await loaded();
    setTime("Daily overview", "23:30");
    setTime("Remind-me-later default", "23:15");
    await userEvent.click(save());
    await screen.findAllByRole("alert");
    return container;
  }

  it("given a 422 for two fields, when shown, then each message sits next to its field and focus goes to the first", async () => {
    const container = await refusedWithTwoProblems();

    const overviewText = "The daily overview at 23:30 would fall inside quiet hours. Try 07:00.";
    const remindText = "The remind-me-later default at 23:15 would fall inside quiet hours. Try 07:00.";
    for (const [label, hint, text] of [
      ["Daily overview", HINTS.overview, overviewText],
      ["Remind-me-later default", HINTS.remind, remindText],
    ] as const) {
      const input = screen.getByLabelText(label);
      expect(input).toHaveAttribute("aria-invalid", "true");
      expect(input).toHaveAccessibleDescription(`${hint} ${text}`);
      expect(screen.getByText(text).closest("[role='alert']")).toHaveTextContent("!");
    }
    expect(screen.getByLabelText("Time zone")).not.toHaveAttribute("aria-invalid");
    expect(screen.getByLabelText("Daily overview")).toHaveFocus();
    expect(save()).toBeEnabled();
    await expectNoAxeViolations(container);
  });

  it("given a refused quiet window, when shown, then the group carries one alert, both times are invalid and focus is on From", async () => {
    const window20to12 = ["quiet_window_length", "20:00 to 12:00", "Try 20:00 to 08:00"] as const;
    wire(() => problems(["quietStart", ...window20to12], ["quietEnd", ...window20to12]));
    await loaded();
    setTime("From", "20:00");
    setTime("Until", "12:00");

    await userEvent.click(save());

    const group = await screen.findByRole("group", { name: "Quiet hours" });
    expect(group.querySelectorAll("[role='alert']")).toHaveLength(1);
    expect(group).toHaveTextContent("Quiet hours can be 1 to 12 hours. 20:00 to 12:00 is 16 hours.");
    expect(screen.getByLabelText("From")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Until")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("From")).toHaveFocus();
  });

  it("given a refused zone, when shown, then the message is next to the zone and focus is on it", async () => {
    wire(() => problems(["timeZone", "zone_unknown", "Mars/Olympus", "Try Europe/Amsterdam"]));
    await loaded();
    setTime("Daily overview", "19:30");

    await userEvent.click(save());

    const zone = screen.getByLabelText("Time zone");
    await waitFor(() => {
      expect(zone).toHaveAttribute("aria-invalid", "true");
    });
    expect(zone).toHaveFocus();
    expect(zone).toHaveAccessibleDescription(/Mars\/Olympus.*Try Europe\/Amsterdam/);
  });

  it("given an error, when the field is edited, then its message goes away and the other stays", async () => {
    await refusedWithTwoProblems();

    setTime("Daily overview", "18:00");

    expect(screen.getByLabelText("Daily overview")).not.toHaveAttribute("aria-invalid");
    expect(screen.getByLabelText("Remind-me-later default")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  it("given a 422 without problems, when shown, then a danger banner asks to check the values and no field is marked", async () => {
    wire(() => json({ type: "about:blank", title: "Unprocessable", status: 422 }, 422));
    await loaded();
    setTime("Daily overview", "19:30");

    await userEvent.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent("Some values were not accepted.");
    expect(document.querySelector("[aria-invalid]")).toBeNull();
  });

  it("given an empty time, when Save is pressed, then nothing is sent and the field asks for a time", async () => {
    const seen = wire();
    await loaded();
    setTime("Daily overview", "");

    await userEvent.click(save());

    expect(await screen.findByText("Pick a time, for example 18:00.")).toBeInTheDocument();
    expect(screen.getByLabelText("Daily overview")).toHaveFocus();
    expect(seen.puts).toHaveLength(0);
  });
});

describe("save failed (criterion 6)", () => {
  it.each([
    ["a 500", () => new Response(null, { status: 500 })],
    ["a network error", () => Promise.reject(new TypeError("Failed to fetch"))],
  ])("given %s, when shown, then the banner keeps the typed values and Try again sends the save again", async (_name, fail) => {
    let attempt = 0;
    const seen = wire(() => (attempt++ === 0 ? fail() : savedAs({ ...VALUES, overviewAt: "19:30" })));
    const container = await loaded();
    setTime("Daily overview", "19:30");

    await userEvent.click(save());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not save. Nothing was changed.");
    expect(alert).toHaveTextContent("Check your connection and try again.");
    expect(screen.getByLabelText("Daily overview")).toHaveValue("19:30");
    expect(save()).toBeEnabled();
    await expectNoAxeViolations(container);

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
    expect(seen.puts.map((p) => p.body.version)).toEqual([3, 3]);
    expect(save()).toBeDisabled();
  });
});

describe("conflict (409): the form takes the new values; U-web-settings-35 adds the words", () => {
  it("given a 409, when it arrives, then the form shows the returned values and the next save uses the new version", async () => {
    const current = { ...STORED, values: { ...VALUES, quietStart: "22:00" }, version: 4, updatedVia: "web" };
    let attempt = 0;
    const seen = wire(() =>
      attempt++ === 0
        ? json({ type: "x", title: "Conflict", status: 409, current }, 409)
        : json({ ...current, version: 5 }),
    );
    await loaded();
    setTime("Daily overview", "19:30");

    await userEvent.click(save());

    await waitFor(() => {
      expect(screen.getByLabelText("From")).toHaveValue("22:00");
    });
    expect(screen.getByLabelText("Daily overview")).toHaveValue("18:00");
    expect(save()).toBeDisabled();
    expect(seen.puts).toHaveLength(1);

    setTime("Daily overview", "19:30");
    await userEvent.click(save());
    await waitFor(() => {
      expect(seen.puts).toHaveLength(2);
    });
    expect(seen.puts[1]?.body.version).toBe(4);
  });
});

describe("security display (criterion 7)", () => {
  it("given the API returns markup as the zone, when rendered, then it is text and no element is created", async () => {
    wire(undefined, () => json({ ...STORED, values: { ...VALUES, timeZone: MARKUP } }));

    const container = await loaded();

    expect(container.querySelector("img")).toBeNull();
    expect(container.innerHTML).not.toContain("<img");
  });

  it("given a refused zone with markup, when the message is shown, then it is text and no element is created", async () => {
    wire(() => problems(["timeZone", "zone_unknown", MARKUP, "Try Europe/Amsterdam"]));
    const container = await loaded();
    setTime("Daily overview", "19:30");

    await userEvent.click(save());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(MARKUP);
    expect(container.querySelector("img")).toBeNull();
  });
});

describe("keyboard only (criterion 8)", () => {
  it("given only the keyboard, when the user tabs, edits, submits an invalid value, fixes it and saves, then the flow works", async () => {
    let attempt = 0;
    const seen = wire(() =>
      attempt++ === 0
        ? problems(["overviewAt", "overview_in_quiet_hours", "23:30", "Try 07:00"])
        : savedAs({ ...VALUES, overviewAt: "18:30" }),
    );
    const user = userEvent.setup();
    await loaded();

    for (const label of ["Time zone", "From", "Until", "Daily overview"]) {
      await user.tab();
      expect(screen.getByLabelText(label)).toHaveFocus();
    }
    setTime("Daily overview", "23:30");
    await user.tab();
    expect(screen.getByLabelText("Remind-me-later default")).toHaveFocus();
    await user.tab();
    expect(save()).toHaveFocus();
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(screen.getByLabelText("Daily overview")).toHaveFocus();
    });
    expect(screen.getByLabelText("Daily overview")).toHaveAttribute("aria-invalid", "true");

    setTime("Daily overview", "18:30");
    await user.tab();
    await user.tab();
    expect(save()).toHaveFocus();
    await user.keyboard(" ");

    await waitFor(() => {
      expect(seen.puts).toHaveLength(2);
    });
    expect(seen.puts[1]?.body.values.overviewAt).toBe("18:30");
    await waitFor(() => {
      expect(save()).toBeDisabled();
    });
  });

  it("given a field with focus, when Enter is pressed, then the form is submitted like Save", async () => {
    const seen = wire();
    await loaded();
    setTime("Daily overview", "19:30");
    screen.getByLabelText("Daily overview").focus();

    await userEvent.keyboard("{Enter}");

    await waitFor(() => {
      expect(seen.puts).toHaveLength(1);
    });
  });
});
