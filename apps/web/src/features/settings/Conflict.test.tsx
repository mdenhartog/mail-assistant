import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, vi } from "vitest";

import { setCsrfToken } from "@/api/client";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { expectNoAxeViolations } from "@/test/axe";

const VALUES = {
  timeZone: "Europe/Amsterdam",
  quietStart: "22:00",
  quietEnd: "07:00",
  overviewAt: "18:00",
  remindAt: "09:00",
};
const STORED = { values: VALUES, version: 1, updatedAt: "2026-11-12T10:00:00Z", updatedVia: "telegram" };
const NEWER = {
  values: { ...VALUES, quietStart: "23:00" },
  version: 2,
  updatedAt: "2026-11-12T13:02:00Z" as string | null,
  updatedVia: "telegram",
};

type Sent = { values: typeof VALUES; version: number };
type Current = typeof NEWER;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function conflict(current: Current): Response {
  return json({ type: "x", title: "Conflict", status: 409, current }, 409);
}

/** GET answers STORED; each PUT answers the next entry of `answers`, the last one for every later PUT. */
function wire(answers: (() => Response)[]): Sent[] {
  const puts: Sent[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const request = new Request(new URL(input, "http://localhost"), init);
      if (request.method === "GET") {
        return json(STORED);
      }
      puts.push((await request.json()) as Sent);
      const answer = answers[Math.min(puts.length - 1, answers.length - 1)];
      return answer ? answer() : json(STORED);
    }),
  );
  return puts;
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

function setTime(label: string, value: string): void {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

const save = (): HTMLElement => screen.getByRole("button", { name: /^(Save changes|Saving\.\.\.)$/ });

/** Marco types 22:30 as the quiet start and saves; Telegram changed it to 23:00 meanwhile. */
async function conflictOnQuietStart(current: Current = NEWER): Promise<Sent[]> {
  const puts = wire([() => conflict(current), () => json({ ...current, version: current.version + 1 })]);
  await loaded();
  setTime("From", "22:30");
  await userEvent.click(save());
  await screen.findByRole("alert");
  return puts;
}

beforeEach(() => {
  setCsrfToken("csrf-secret-4711");
});

afterEach(() => {
  setCsrfToken(null);
  vi.unstubAllGlobals();
});

describe("conflict banner (criteria 1 and 6)", () => {
  it("given a 409, when shown, then the banner names Telegram and the Amsterdam time, has focus and the new values show", async () => {
    await conflictOnQuietStart();

    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent(
      "Settings changed in Telegram at 14:02 (Amsterdam time). I loaded the new values. Nothing is saved until you press Save again.",
    );
    expect(banner).toHaveFocus();
    expect(screen.getByLabelText("From")).toHaveValue("23:00");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  it("given the other change came from the web, when shown, then the banner says from the web", async () => {
    await conflictOnQuietStart({ ...NEWER, updatedVia: "web" });

    expect(screen.getByRole("alert")).toHaveTextContent("Settings changed from the web at 14:02 (Amsterdam time).");
  });

  it("given a change without a time, when shown, then the banner names the source and no time", async () => {
    await conflictOnQuietStart({ ...NEWER, updatedAt: null });

    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent("Settings changed in Telegram.");
    expect(banner).not.toHaveTextContent("Amsterdam time");
  });
});

describe("marks on edited fields (criterion 2)", () => {
  it("given quiet start edited and changed by Telegram, when shown, then only that field is marked with both buttons", async () => {
    await conflictOnQuietStart();

    expect(screen.getAllByText(/You typed/)).toHaveLength(1);
    expect(screen.getByText("You typed 22:30, Telegram now has 23:00")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use mine for Quiet hours from" })).toHaveTextContent("Use mine");
    expect(screen.getByRole("button", { name: "Keep Telegram's for Quiet hours from" })).toHaveTextContent(
      "Keep Telegram's",
    );
  });

  it("given a field edited and put back, when a 409 arrives, then it is not marked", async () => {
    wire([() => conflict(NEWER)]);
    await loaded();
    setTime("Daily overview", "19:30");
    setTime("Daily overview", "18:00");
    setTime("Until", "07:30");
    await userEvent.click(save());
    await screen.findByRole("alert");

    expect(screen.getAllByText(/You typed/)).toHaveLength(1);
    expect(screen.getByText("You typed 07:30, Telegram now has 07:00")).toBeInTheDocument();
  });

  it("given I typed what Telegram now has, when a 409 arrives, then there is nothing to choose and no mark", async () => {
    wire([() => conflict(NEWER)]);
    await loaded();
    setTime("From", "23:00");
    setTime("Until", "07:30");
    await userEvent.click(save());
    await screen.findByRole("alert");

    expect(screen.queryByText("You typed 23:00, Telegram now has 23:00")).not.toBeInTheDocument();
    expect(screen.getAllByText(/You typed/)).toHaveLength(1);
  });
});

describe("Use mine and Keep Telegram's (criteria 3 and 4)", () => {
  it("given Use mine, when pressed, then the field holds the typed value again, unsaved", async () => {
    const puts = await conflictOnQuietStart();

    await userEvent.click(screen.getByRole("button", { name: "Use mine for Quiet hours from" }));

    expect(screen.getByLabelText("From")).toHaveValue("22:30");
    expect(screen.getByText("Using your value.")).toBeInTheDocument();
    expect(save()).toBeEnabled();
    expect(puts).toHaveLength(1);
  });

  it("given Keep Telegram's, when pressed after Use mine, then the mark is gone and the field holds Telegram's value", async () => {
    await conflictOnQuietStart();
    await userEvent.click(screen.getByRole("button", { name: "Use mine for Quiet hours from" }));

    await userEvent.click(screen.getByRole("button", { name: "Keep Telegram's for Quiet hours from" }));

    expect(screen.queryByText(/You typed/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("From")).toHaveValue("23:00");
  });

  it("given the last mark is dismissed, when Keep Telegram's is pressed, then focus does not fall back to the page", async () => {
    await conflictOnQuietStart();

    await userEvent.click(screen.getByRole("button", { name: "Keep Telegram's for Quiet hours from" }));

    expect(document.body).not.toHaveFocus();
  });

  it("given a mark, when the field is edited to a third value, then its mark goes away", async () => {
    await conflictOnQuietStart();

    setTime("From", "21:15");

    expect(screen.queryByText(/You typed/)).not.toBeInTheDocument();
  });
});

describe("nothing is saved by itself (criterion 5)", () => {
  it("given the conflict and no press, when time passes, then nothing is sent and Save sends the new version", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const puts = await conflictOnQuietStart();
      await vi.advanceTimersByTimeAsync(60_000);
      expect(puts).toHaveLength(1);

      await userEvent.click(screen.getByRole("button", { name: "Use mine for Quiet hours from" }));
      await userEvent.click(save());

      await waitFor(() => {
        expect(puts).toHaveLength(2);
      });
      expect(puts[1]).toEqual({ values: { ...VALUES, quietStart: "22:30" }, version: 2 });
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("a second 409 while resolving (criterion 7)", () => {
  it("given a second conflict, when it arrives, then banner and marks are recomputed against the newest values", async () => {
    const second = { ...NEWER, values: { ...VALUES, quietStart: "23:30" }, version: 3, updatedVia: "web" };
    const puts = wire([() => conflict(NEWER), () => conflict(second)]);
    await loaded();
    setTime("From", "22:30");
    await userEvent.click(save());
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: "Use mine for Quiet hours from" }));

    await userEvent.click(save());

    await screen.findByText("You typed 22:30, the web now has 23:30");
    expect(puts.map((p) => p.version)).toEqual([1, 2]);
    expect(screen.getByRole("alert")).toHaveTextContent("Settings changed from the web");
    expect(screen.getByRole("alert")).toHaveFocus();
    expect(screen.getAllByText(/You typed/)).toHaveLength(1);
    expect(screen.getByLabelText("From")).toHaveValue("23:30");
  });
});

describe("screen reader and axe (criterion 8)", () => {
  it("given several marks, when read, then each button is named with its field and axe finds nothing", async () => {
    wire([() => conflict({ ...NEWER, values: { ...VALUES, quietStart: "23:00", overviewAt: "17:00" } })]);
    const container = await loaded();
    setTime("From", "22:30");
    setTime("Daily overview", "19:30");
    await userEvent.click(save());
    await screen.findByRole("alert");

    for (const name of ["Quiet hours from", "Daily overview"]) {
      expect(screen.getByRole("button", { name: `Use mine for ${name}` })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: `Keep Telegram's for ${name}` })).toBeInTheDocument();
    }
    expect(screen.getAllByRole("button", { name: /^Use mine for / })).toHaveLength(2);
    expect(within(screen.getByRole("alert")).queryAllByRole("button")).toHaveLength(0);
    await expectNoAxeViolations(container);
  });
});
