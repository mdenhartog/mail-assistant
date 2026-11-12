import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, vi } from "vitest";

import { ZoneField } from "@/features/settings/ZoneField";
import { expectNoAxeViolations } from "@/test/axe";

interface Place {
  zone: string;
  label: string;
  utcOffsetMinutes: number;
}
interface Answer {
  places: Place[];
  suggestion?: string | null;
}

const BANGKOK: Place = { zone: "Asia/Bangkok", label: "Bangkok, Thailand (UTC+7)", utcOffsetMinutes: 420 };
const BANGKA: Place = { zone: "Asia/Jakarta", label: "Bangka, Indonesia (UTC+7)", utcOffsetMinutes: 420 };
const BANGALORE: Place = { zone: "Asia/Kolkata", label: "Bangalore, India (UTC+5:30)", utcOffsetMinutes: 330 };
const AMSTERDAM: Place = { zone: "Europe/Amsterdam", label: "Amsterdam, Netherlands (UTC+1)", utcOffsetMinutes: 60 };
const BASE_ANSWERS: Record<string, Answer> = {
  bang: { places: [BANGKOK, BANGKA, BANGALORE] },
  bangk: { places: [BANGKOK] },
  amst: { places: [AMSTERDAM] },
  phuket: { places: [], suggestion: "Bangkok" },
  nothing: { places: [] },
};
let ANSWERS: Record<string, Answer> = { ...BASE_ANSWERS };
/** 20:42 UTC: 21:42 in Amsterdam, 03:42 the next day in Bangkok. */
const EVENING = new Date("2026-11-12T20:42:00Z");

type Gate = { release: () => void };
const requested: string[] = [];
let gates: Record<string, Promise<void>> = {};

function stubPlaces(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      const query = new URL(input, "http://localhost").searchParams.get("q") ?? "";
      requested.push(query);
      await gates[query];
      const body = ANSWERS[query] ?? { places: [] };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
}

function holdAnswer(query: string): Gate {
  let release = (): void => undefined;
  gates[query] = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { release };
}

interface HarnessProps {
  initial?: string;
  saved?: string;
  readOnly?: boolean;
  error?: string;
  clock?: () => Date;
  onValue?: (zone: string) => void;
}

function Harness({ initial = "Europe/Amsterdam", saved, readOnly = false, error, clock, onValue }: HarnessProps): ReactElement {
  const [value, setValue] = useState(initial);
  return (
    <ZoneField
      error={error}
      now={clock ?? (() => EVENING)}
      onChange={(next) => {
        setValue(next);
        onValue?.(next);
      }}
      readOnly={readOnly}
      savedValue={saved ?? initial}
      value={value}
    />
  );
}

function setup(props: HarnessProps = {}): { user: ReturnType<typeof userEvent.setup>; input: HTMLElement; container: HTMLElement } {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const user = userEvent.setup();
  const { container } = render(
    <QueryClientProvider client={client}>
      <Harness {...props} />
    </QueryClientProvider>,
  );
  return { user, input: screen.getByRole("combobox", { name: "Time zone" }), container };
}

async function typeAndWait(user: ReturnType<typeof userEvent.setup>, input: HTMLElement, text: string): Promise<void> {
  await user.clear(input);
  await user.type(input, text);
  await screen.findByRole("listbox", {}, { timeout: 2000 });
}

beforeEach(() => {
  requested.length = 0;
  gates = {};
  ANSWERS = { ...BASE_ANSWERS };
  stubPlaces();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("ZoneCombobox", () => {
  it("given the combobox, when opened and closed, then the ARIA 1.2 attributes follow (AC-23, C-7)", async () => {
    const { user, input } = setup();
    expect(input).toHaveAttribute("aria-autocomplete", "list");
    expect(input).toHaveAttribute("aria-expanded", "false");
    expect(input).not.toHaveAttribute("aria-activedescendant");
    const listId = input.getAttribute("aria-controls");
    expect(listId).toBeTruthy();

    await typeAndWait(user, input, "bang");
    expect(input).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("listbox")).toHaveAttribute("id", listId);
    await user.keyboard("{ArrowDown}");
    const first = screen.getAllByRole("option")[0];
    expect(input).toHaveAttribute("aria-activedescendant", first?.id);
    expect(first).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{Escape}");
    expect(input).toHaveAttribute("aria-expanded", "false");
    expect(input).not.toHaveAttribute("aria-activedescendant");
    expect(document.getElementById(listId ?? "")).not.toBeNull();
  });

  it("given the user types bang, when the search resolves, then the options carry the local time and the count is announced (C-7)", async () => {
    const { user, input } = setup({ initial: "Asia/Bangkok" });
    await typeAndWait(user, input, "bang");
    const options = screen.getAllByRole("option");
    expect(options.map((option) => option.getAttribute("aria-label"))).toEqual([
      "Bangkok, Thailand, UTC+7, 03:42 now",
      "Bangka, Indonesia, UTC+7, 03:42 now",
      "Bangalore, India, UTC+5:30, 02:12 now",
    ]);
    expect(screen.getByText("3 places found")).toBeInTheDocument();
    expect(screen.getByText("3 places found").closest("[aria-live]")).toHaveAttribute("aria-live", "polite");
  });

  it("given another day than the saved zone, when listed, then the option says tomorrow (C-7)", async () => {
    const { user, input } = setup();
    await typeAndWait(user, input, "bangk");
    expect(screen.getByRole("option")).toHaveAttribute("aria-label", "Bangkok, Thailand, UTC+7, 03:42 now (tomorrow)");
  });

  it("given the saved zone is ahead, when listed, then the option says yesterday (C-7)", async () => {
    const { user, input } = setup({ initial: "Asia/Bangkok", clock: () => new Date("2026-11-12T20:42:00Z") });
    await typeAndWait(user, input, "amst");
    expect(screen.getByRole("option")).toHaveAttribute("aria-label", "Amsterdam, Netherlands, UTC+1, 21:42 now (yesterday)");
  });

  it("given the keyboard, when the keys are used, then the active option moves and focus stays in the input (AC-23)", async () => {
    const onValue = vi.fn();
    const { user, input } = setup({ onValue });
    await typeAndWait(user, input, "bang");
    const options = screen.getAllByRole("option");
    await user.keyboard("{ArrowDown}");
    expect(input).toHaveAttribute("aria-activedescendant", options[0]?.id);
    await user.keyboard("{ArrowDown}");
    expect(input).toHaveAttribute("aria-activedescendant", options[1]?.id);
    await user.keyboard("{ArrowUp}{ArrowUp}");
    expect(input).toHaveAttribute("aria-activedescendant", options[2]?.id);
    expect(input).toHaveFocus();

    await user.keyboard("{Home}");
    expect(input).toHaveAttribute("aria-activedescendant", options[2]?.id);
    await user.keyboard("{End}");
    expect(input).toHaveAttribute("aria-activedescendant", options[2]?.id);

    await user.keyboard("{ArrowUp}{Enter}");
    expect(onValue).toHaveBeenLastCalledWith("Asia/Jakarta");
    expect(input).toHaveAttribute("aria-expanded", "false");
    expect(input).toHaveFocus();
  });

  it("given an open list, when Escape is pressed twice, then the list closes and the saved zone returns (AC-23)", async () => {
    const onValue = vi.fn();
    const { user, input } = setup({ onValue });
    await typeAndWait(user, input, "bangk");
    await user.keyboard("{ArrowDown}{Enter}");
    expect(onValue).toHaveBeenLastCalledWith("Asia/Bangkok");
    expect(input).toHaveValue("Asia/Bangkok");
    await typeAndWait(user, input, "bang");

    await user.keyboard("{Escape}");
    expect(input).toHaveAttribute("aria-expanded", "false");
    expect(input).toHaveValue("bang");
    await user.keyboard("{Escape}");
    expect(onValue).toHaveBeenLastCalledWith("Europe/Amsterdam");
    expect(input).toHaveValue("Europe/Amsterdam");
  });

  it("given typed text and no selection, when Tab is pressed, then nothing is accepted (AC-23)", async () => {
    const onValue = vi.fn();
    const { user, input } = setup({ onValue });
    await typeAndWait(user, input, "bang");
    await user.keyboard("{ArrowDown}{Tab}");
    expect(onValue).not.toHaveBeenCalled();
    expect(input).toHaveValue("Europe/Amsterdam");
    expect(input).toHaveAttribute("aria-expanded", "false");
  });

  it("given Enter without an active option, when the list has several places, then nothing is chosen (AC-23)", async () => {
    const onValue = vi.fn();
    const { user, input } = setup({ onValue });
    await typeAndWait(user, input, "bang");
    await user.keyboard("{Enter}");
    expect(onValue).not.toHaveBeenCalled();
  });

  it("given a chosen zone, when the user pauses and on selection, then the live paragraph tells the local time (AC-28, C-7)", async () => {
    const { user, input } = setup();
    const live = screen.getByText("In Amsterdam it is 21:42 right now.");
    expect(live.closest("[aria-live]")).toHaveAttribute("aria-live", "polite");

    await typeAndWait(user, input, "bangk");
    await user.keyboard("{ArrowDown}{Enter}");
    expect(await screen.findByText("In Bangkok it is 03:42 right now.")).toBeInTheDocument();
  });

  it("given the paragraph, when the clock is on both sides of a clock change, then the local time follows (AC-28)", () => {
    const { unmount } = render(
      <QueryClientProvider client={new QueryClient()}>
        <Harness clock={() => new Date("2026-03-29T00:30:00Z")} />
      </QueryClientProvider>,
    );
    expect(screen.getByText("In Amsterdam it is 01:30 right now.")).toBeInTheDocument();
    unmount();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <Harness clock={() => new Date("2026-03-29T01:30:00Z")} />
      </QueryClientProvider>,
    );
    expect(screen.getByText("In Amsterdam it is 03:30 right now.")).toBeInTheDocument();
  });

  it("given the typing pauses, when 300 ms pass, then the paragraph previews the first place (C-7)", async () => {
    const { user, input } = setup();
    await typeAndWait(user, input, "bangk");
    expect(screen.queryByText("In Bangkok it is 03:42 right now.")).not.toBeInTheDocument();
    expect(await screen.findByText("In Bangkok it is 03:42 right now.", {}, { timeout: 2000 })).toBeInTheDocument();
  });

  it("given text with no match, when the search is empty, then a hint and the suggestion show, not an alert (C-7)", async () => {
    const { user, input } = setup();
    await user.clear(input);
    await user.type(input, "phuket");
    const hint = await screen.findByText("Nothing found for 'phuket'. Try the nearest bigger city, or the country.", {}, { timeout: 2000 });
    expect(hint.closest("[role='alert']")).toBeNull();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(input).toHaveAttribute("aria-expanded", "false");
    await user.click(screen.getByRole("button", { name: "Did you mean Bangkok?" }));
    expect(input).toHaveValue("Bangkok");
  });

  it("given unselected text, when the field loses focus, then the saved value returns and is never empty (AC-23)", async () => {
    const { user, input } = setup();
    await typeAndWait(user, input, "bang");
    await user.tab();
    expect(input).toHaveValue("Europe/Amsterdam");

    await user.click(input);
    await user.clear(input);
    await user.tab();
    expect(input).toHaveValue("Europe/Amsterdam");
  });

  it("given a place label with markup, when shown, then it is text only (AC-14)", async () => {
    const markup = "<img src=x onerror=alert(1)>";
    ANSWERS["bang"] = { places: [{ zone: "Asia/Bangkok", label: `${markup}, Thailand (UTC+7)`, utcOffsetMinutes: 420 }] };
    const { user, input } = setup();
    await typeAndWait(user, input, "bang");
    const list = screen.getByRole("listbox");
    expect(within(list).getByText(`${markup}, Thailand`)).toBeInTheDocument();
    expect(list.querySelector("img")).toBeNull();
  });

  it("given two searches where the first answers late, when both resolve, then only the latest shows (C-7)", async () => {
    const slow = holdAnswer("bang");
    const { user, input } = setup();
    await user.clear(input);
    await user.type(input, "bang");
    await waitFor(() => {
      expect(requested).toContain("bang");
    });
    await user.type(input, "k");
    await screen.findByRole("listbox", {}, { timeout: 2000 });
    expect(screen.getAllByRole("option")).toHaveLength(1);
    await act(async () => {
      slow.release();
      await Promise.resolve();
    });
    expect(screen.getAllByRole("option")).toHaveLength(1);
    expect(screen.getByRole("option")).toHaveAttribute("aria-label", expect.stringContaining("Bangkok"));
  });

  it("given the typed query, when the page is inspected, then it is in no URL, storage or log (W-15)", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((method) => vi.spyOn(console, method));
    const before = window.location.href;
    const { user, input } = setup();
    await typeAndWait(user, input, "bang");
    await user.keyboard("{ArrowDown}{Enter}");
    expect(window.location.href).toBe(before);
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    for (const spy of spies) {
      expect(JSON.stringify(spy.mock.calls)).not.toContain("bang");
    }
  });

  it("given a debounced typing burst, when typed, then one request is sent for the final text", async () => {
    const { user, input } = setup();
    await typeAndWait(user, input, "bang");
    expect(requested).toEqual(["bang"]);
  });

  it("given a read-only form, when the field is shown, then the input is read-only and opens nothing", async () => {
    const { user, input } = setup({ readOnly: true });
    expect(input).toHaveAttribute("readonly");
    input.focus();
    await user.keyboard("{ArrowDown}");
    expect(input).toHaveAttribute("aria-expanded", "false");
    expect(requested).toEqual([]);
  });

  it("given the stored zone, when shown, then it reads Currently: and the field shows the zone", () => {
    setup();
    expect(screen.getByText("Currently: Europe/Amsterdam")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Time zone" })).toHaveValue("Europe/Amsterdam");
  });

  it("given a refused zone, when shown, then the field is invalid and keeps the hint (AC-23)", () => {
    setup({ error: "I do not know that zone." });
    const input = screen.getByRole("combobox", { name: "Time zone" });
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription(/The times below are local times in this zone\..*I do not know that zone\./);
  });

  it("given the closed, open, empty and no-result states, when axe runs, then no violation (AC-22)", async () => {
    const { user, input, container } = setup();
    await expectNoAxeViolations(container);

    await typeAndWait(user, input, "bang");
    await user.keyboard("{ArrowDown}");
    await expectNoAxeViolations(container);

    await user.clear(input);
    await expectNoAxeViolations(container);

    await user.type(input, "phuket");
    await screen.findByText(/Nothing found for/, {}, { timeout: 2000 });
    await expectNoAxeViolations(container);
  });
});
