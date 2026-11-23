import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { expectNoAxeViolations } from "@/test/axe";
import { INVOICES, NO_OPEN_PLAN, json, renderPage, wire } from "@/test/categories";

afterEach(() => {
  vi.unstubAllGlobals();
});

const BUTTON = "Sort everything again";
const FIELD = "Confidence threshold (%)";
const REASON = "Use a whole number from 50 to 100.";
const REQUEST_ID = "5b0c1c2e-1b1e-4c52-9d0e-0a6a1b1c00bb";

async function loaded(): Promise<HTMLElement> {
  const container = renderPage();
  await screen.findByRole("button", { name: `Edit ${INVOICES.name}` });
  await screen.findByRole("textbox", { name: FIELD });
  return container;
}

function field(): HTMLElement {
  return screen.getByRole("textbox", { name: FIELD });
}

async function typeInto(text: string): Promise<void> {
  const box = field();
  await userEvent.clear(box);
  if (text !== "") {
    await userEvent.type(box, text);
  }
}

function sentence(x: string): string {
  return `Mail from a sender rule always moves. Everything else the model is at least ${x} % sure of moves by itself after a short delay, and each can be undone with Move back.`;
}

describe("Sort everything again: the threshold field (criterion 1, AC-45)", () => {
  it("given the first visit, then the field shows 50", async () => {
    wire();
    await loaded();
    expect(field()).toHaveValue("50");
  });

  it("given a later visit, then the field shows the latest request", async () => {
    wire({ latest: () => json({ threshold: 80 }) });
    await loaded();
    expect(field()).toHaveValue("80");
  });

  it("given the latest request is loading, then a loading text shows and the button is not there yet", async () => {
    wire({ latest: () => new Promise<Response>(() => undefined) });
    renderPage();
    await screen.findByRole("button", { name: `Edit ${INVOICES.name}` });
    expect(await screen.findByText("Loading the threshold")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: BUTTON })).not.toBeInTheDocument();
  });

  it("given the latest request cannot be read, then a friendly error offers to try again", async () => {
    let calls = 0;
    wire({ latest: () => (++calls === 1 ? json({}, 500) : json({ threshold: 70 })) });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("textbox", { name: FIELD })).toHaveValue("70");
  });
});

describe("Sort everything again: the checks before a request (criterion 2, AC-45)", () => {
  it.each(["49", "50.5", "50 ", "abc", "101", "1000", "", "-60", "5e1"])(
    "given %j, when the button is pressed, then the field shows the reason, gets focus and no request is made",
    async (text) => {
      const seen = wire();
      await loaded();
      await typeInto(text);

      await userEvent.click(screen.getByRole("button", { name: BUTTON }));

      expect(await screen.findByRole("alert")).toHaveTextContent(REASON);
      expect(field()).toHaveFocus();
      expect(field()).toHaveAttribute("aria-invalid", "true");
      expect(field()).toHaveAccessibleDescription(new RegExp(REASON));
      expect(seen.resorts).toHaveLength(0);
    },
  );

  it.each([
    ["50", 50],
    ["100", 100],
    ["73", 73],
  ])("given %s, when the button is pressed, then one request with the number %i is made", async (text, expected) => {
    const seen = wire({ resort: () => json({ requestId: REQUEST_ID, threshold: expected }, 201) });
    await loaded();
    await typeInto(text);

    await userEvent.click(screen.getByRole("button", { name: BUTTON }));

    expect(await screen.findByText(/Your request is in/)).toBeInTheDocument();
    expect(seen.resorts).toEqual([{ threshold: expected }]);
  });

  it("given a reason is shown, when the user types again, then the reason goes away", async () => {
    wire();
    await loaded();
    await typeInto("abc");
    await userEvent.click(screen.getByRole("button", { name: BUTTON }));
    await screen.findByRole("alert");

    await typeInto("60");

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(field()).not.toHaveAttribute("aria-invalid");
  });

  it("given a request was made, then the button is disabled with the reason", async () => {
    wire();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: BUTTON }));
    await screen.findByText(/Your request is in/);

    const button = screen.getByRole("button", { name: BUTTON });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(/Your request is in/);
  });

  it("given the api says a plan is open (409), then its reason shows beside the button", async () => {
    wire({ resort: () => json({}, 409) });
    await loaded();

    await userEvent.click(screen.getByRole("button", { name: BUTTON }));

    const reason = await screen.findByRole("alert");
    expect(reason).toHaveTextContent("A plan is already open or being prepared. Wait until it has been applied or cancelled.");
    expect(screen.getByRole("button", { name: BUTTON })).toHaveAccessibleDescription(/already open/);
  });

  it.each([
    [429, /Too many requests/],
    [500, /Could not send your request/],
  ])("given the api answers %i, then a friendly message shows", async (status, text) => {
    wire({ resort: () => json({}, status) });
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: BUTTON }));
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
  });
});

describe("Sort everything again: an open plan (criterion 3, AC-46)", () => {
  it.each(["building", "ready", "scheduled", "applying"])(
    "given a plan in state %s, then the button is disabled with the reason",
    async (state) => {
      wire({ plan: () => json({ ...NO_OPEN_PLAN, id: "5b0c1c2e-1b1e-4c52-9d0e-0a6a1b1c00aa", state }) });
      await loaded();

      await vi.waitFor(() => {
        expect(screen.getByRole("button", { name: BUTTON })).toBeDisabled();
      });
      expect(screen.getByRole("button", { name: BUTTON })).toHaveAccessibleDescription(/A plan is open/);
      expect(screen.getByRole("link", { name: "Follow it in Review moves" })).toHaveAttribute("href", "/review");
      expect(screen.getByRole("link", { name: "Follow it in Review moves" })).toHaveClass("min-h-11");
    },
  );

  it("given no plan is open, then the button is enabled", async () => {
    wire();
    await loaded();
    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: BUTTON })).toBeEnabled();
    });
    expect(screen.queryByText(/A plan is open/)).not.toBeInTheDocument();
  });

  it("given the plan cannot be read, then the button stays usable (the api refuses with a 409 when needed)", async () => {
    wire({ plan: () => json({}, 500) });
    await loaded();
    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: BUTTON })).toBeEnabled();
    });
  });
});

describe("Sort everything again: the texts (criterion 4, AC-68)", () => {
  it("given the first visit, then the texts match the spec word for word with 50", async () => {
    wire();
    await loaded();
    expect(screen.getByText(sentence("50"))).toBeInTheDocument();
    expect(screen.getByText("Nothing moves until a short delay; you can cancel in Telegram.")).toBeInTheDocument();
  });

  it("given a typed valid threshold, then the text shows it; an invalid one keeps the last valid one", async () => {
    wire({ latest: () => json({ threshold: 80 }) });
    await loaded();
    expect(screen.getByText(sentence("80"))).toBeInTheDocument();

    await typeInto("95");
    expect(screen.getByText(sentence("95"))).toBeInTheDocument();
    await typeInto("9x");
    expect(screen.getByText(sentence("95"))).toBeInTheDocument();
  });

  it("given the page, then the fixed block says again to press Sort everything again", async () => {
    wire();
    await loaded();
    expect(
      screen.getByText(
        "Changing the list never moves mail you already have. Only new mail follows it. To re-sort the inbox, press Sort everything again.",
      ),
    ).toBeInTheDocument();
  });

  it("given the page, then it says the confidence is the model's own report", async () => {
    wire();
    await loaded();
    expect(screen.getByText("The model's confidence is its own estimate, not a calibrated probability.")).toBeInTheDocument();
  });
});

describe("Sort everything again: keyboard and screen reader (criterion 6, AC-67)", () => {
  it("given the field, then it is labelled, described by the sentence and followed by the button in tab order", async () => {
    wire();
    await loaded();
    expect(field()).toHaveAccessibleDescription(/Mail from a sender rule always moves/);
    expect(field()).toHaveAttribute("inputmode", "numeric");

    field().focus();
    await userEvent.tab();
    expect(screen.getByRole("button", { name: BUTTON })).toHaveFocus();
    expect(screen.getByRole("button", { name: BUTTON })).toHaveAccessibleDescription(/Nothing moves until a short delay/);
  });

  it("given a threshold, when Enter is pressed in the field, then the request is made", async () => {
    const seen = wire();
    await loaded();
    await typeInto("65");
    await userEvent.type(field(), "{Enter}");
    expect(await screen.findByText(/Your request is in/)).toBeInTheDocument();
    expect(seen.resorts).toEqual([{ threshold: 65 }]);
  });

  it("given the field and the button, then every control is at least 44 px", async () => {
    wire();
    await loaded();
    expect(field()).toHaveClass("min-h-11");
    expect(screen.getByRole("button", { name: BUTTON })).toHaveClass("min-h-11");
  });

  it("given an open plan, then axe finds no violations", async () => {
    wire({ plan: () => json({ ...NO_OPEN_PLAN, state: "ready", id: "x" }) });
    const container = await loaded();
    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: BUTTON })).toBeDisabled();
    });
    await expectNoAxeViolations(container);
  });

  it("given an error on the field, then axe finds no violations", async () => {
    wire();
    const container = await loaded();
    await typeInto("abc");
    await userEvent.click(screen.getByRole("button", { name: BUTTON }));
    await screen.findByRole("alert");
    await expectNoAxeViolations(container);
    expect(within(screen.getByRole("alert")).getByText(REASON)).toBeInTheDocument();
  });
});
