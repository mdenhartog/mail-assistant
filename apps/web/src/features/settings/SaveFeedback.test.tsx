import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { SaveFeedback } from "@/features/settings/SaveFeedback";
import type { Settings } from "@/features/settings/useSettings";
import { convertClock, minutesPhrase } from "@/features/settings/zoneMath";
import { expectNoAxeViolations } from "@/test/axe";

const AMS = {
  timeZone: "Europe/Amsterdam",
  quietStart: "23:00",
  quietEnd: "07:00",
  overviewAt: "18:00",
  remindAt: "09:00",
};
const BKK = { ...AMS, timeZone: "Asia/Bangkok" };
const FROM_TELEGRAM: Settings = { values: AMS, version: 3, updatedAt: "2026-11-12T13:02:00Z", updatedVia: "telegram" };
const NOW = (): Date => new Date("2026-11-12T15:00:00Z");

function stubSession(minutes: number | null): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => {
      if (minutes === null) {
        return Promise.resolve(new Response("{}", { status: 500 }));
      }
      const body = {
        maskedAddress: "m***@example.org",
        csrfToken: "t",
        idleExpiresAt: "2026-11-12T16:00:00Z",
        absoluteExpiresAt: "2026-11-12T20:00:00Z",
        noticeIntervalMinutes: minutes,
      };
      return Promise.resolve(
        new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }),
      );
    }),
  );
}

function renderFeedback(props: { settings: Settings; values: Settings["values"]; saved?: Settings | null }): HTMLElement {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SaveFeedback now={NOW} saved={props.saved ?? null} settings={props.settings} values={props.values} />
    </QueryClientProvider>,
  ).container;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("last-change line", () => {
  it("names Telegram and the time in the stored zone, with a time element", () => {
    stubSession(5);
    renderFeedback({ settings: FROM_TELEGRAM, values: AMS });
    const line = screen.getByText(/Last changed from Telegram at/);
    expect(line).toHaveTextContent("Last changed from Telegram at 14:02");
    expect(line.querySelector("time")).toHaveAttribute("datetime", "2026-11-12T13:02:00Z");
  });

  it("says from the web", () => {
    stubSession(5);
    renderFeedback({ settings: { ...FROM_TELEGRAM, updatedVia: "web" }, values: AMS });
    expect(screen.getByText(/Last changed from the web at/)).toHaveTextContent("at 14:02");
  });

  it("says the defaults are used at version 0", () => {
    stubSession(5);
    renderFeedback({
      settings: { values: AMS, version: 0, updatedAt: null, updatedVia: null },
      values: AMS,
    });
    expect(screen.getByText("Using the default settings.")).toBeInTheDocument();
    expect(screen.queryByText(/Last changed/)).not.toBeInTheDocument();
  });
});

describe("saved banner", () => {
  const saved: Settings = { values: BKK, version: 4, updatedAt: "2026-11-12T14:42:00Z", updatedVia: "web" };

  it("states what is true now with the interval from the session", async () => {
    stubSession(5);
    renderFeedback({ settings: saved, values: BKK, saved });
    const banner = await screen.findByRole("status");
    await vi.waitFor(() => {
      expect(banner).toHaveTextContent(
        "Saved at 21:42. Quiet hours are 23:00 to 07:00 (Bangkok time). " +
          "A message with an Undo button follows on Telegram within about 5 minutes.",
      );
    });
    expect(screen.getByText(/Last changed from the web at/)).toHaveTextContent("at 21:42");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("still confirms the save when the interval is unknown", async () => {
    stubSession(null);
    renderFeedback({ settings: saved, values: BKK, saved });
    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent("Saved at 21:42. Quiet hours are 23:00 to 07:00 (Bangkok time).");
    await vi.waitFor(() => {
      expect(banner).toHaveTextContent("A message with an Undo button follows on Telegram shortly.");
    });
  });

  it("shows no banner before a save", () => {
    stubSession(5);
    renderFeedback({ settings: FROM_TELEGRAM, values: AMS });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("has no axe violations with banner and preview", async () => {
    stubSession(5);
    const container = renderFeedback({ settings: saved, values: AMS, saved });
    await screen.findByRole("status");
    await expectNoAxeViolations(container);
  });
});

describe("minutesPhrase", () => {
  it("uses the singular for one minute", () => {
    expect(minutesPhrase(1)).toBe("about 1 minute");
    expect(minutesPhrase(5)).toBe("about 5 minutes");
  });
});

describe("zone preview", () => {
  it("shows the new zone and the same moment in the stored zone", () => {
    stubSession(5);
    renderFeedback({ settings: FROM_TELEGRAM, values: { ...BKK, quietStart: "22:00" } });
    expect(
      screen.getByText("Quiet hours will now be 22:00 to 07:00 Bangkok time (16:00 to 01:00 Amsterdam time)."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("disappears when the zone is the stored one again", () => {
    stubSession(5);
    renderFeedback({ settings: FROM_TELEGRAM, values: AMS });
    expect(screen.queryByText(/Quiet hours will now be/)).not.toBeInTheDocument();
  });

  it("is hidden for a zone that is not known", () => {
    stubSession(5);
    renderFeedback({ settings: FROM_TELEGRAM, values: { ...AMS, timeZone: "Bangk" } });
    expect(screen.queryByText(/Quiet hours will now be/)).not.toBeInTheDocument();
  });
});

describe("permanent sentence", () => {
  it("is always present", () => {
    stubSession(5);
    renderFeedback({ settings: FROM_TELEGRAM, values: AMS });
    expect(screen.getByText("Quiet hours, the overview and reminders follow this time zone.")).toBeInTheDocument();
  });
});

describe("convertClock", () => {
  const at = new Date("2026-11-12T15:00:00Z");

  it("converts between zones", () => {
    expect(convertClock("22:00", "Asia/Bangkok", "Europe/Amsterdam", at)).toEqual({ clock: "16:00", dayNote: "" });
  });

  it("handles a half-hour offset", () => {
    expect(convertClock("07:00", "Asia/Kolkata", "Europe/Amsterdam", at)?.clock).toBe("02:30");
  });

  it("notes a day boundary", () => {
    expect(convertClock("01:00", "Asia/Bangkok", "Europe/Amsterdam", at)).toEqual({
      clock: "19:00",
      dayNote: " (yesterday)",
    });
    expect(convertClock("23:00", "America/Los_Angeles", "Europe/Amsterdam", at)).toEqual({
      clock: "08:00",
      dayNote: " (tomorrow)",
    });
  });

  it("uses the offsets of the injected date", () => {
    const summer = new Date("2026-07-01T12:00:00Z");
    expect(convertClock("22:00", "Asia/Bangkok", "Europe/Amsterdam", summer)?.clock).toBe("17:00");
    const dayBeforeChange = new Date("2026-03-28T12:00:00Z");
    const dayAfterChange = new Date("2026-03-29T12:00:00Z");
    expect(convertClock("12:00", "Europe/Amsterdam", "UTC", dayBeforeChange)?.clock).toBe("11:00");
    expect(convertClock("12:00", "Europe/Amsterdam", "UTC", dayAfterChange)?.clock).toBe("10:00");
  });

  it("returns null for an unknown zone or a bad clock", () => {
    expect(convertClock("22:00", "Nowhere", "UTC", at)).toBeNull();
    expect(convertClock("later", "UTC", "UTC", at)).toBeNull();
  });
});
