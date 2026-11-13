import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { ConflictLayer } from "@/features/settings/ConflictLayer";
import type { ConflictState, SettingsValues } from "@/features/settings/useSettings";
import { expectNoAxeViolations } from "@/test/axe";

const BASE: SettingsValues = {
  timeZone: "Europe/Amsterdam",
  quietStart: "22:00",
  quietEnd: "07:00",
  overviewAt: "18:00",
  remindAt: "09:00",
};
const MINE: SettingsValues = { ...BASE, quietStart: "22:30" };

function conflictVia(updatedVia: "web" | "telegram" | null): ConflictState {
  return {
    base: BASE,
    mine: MINE,
    current: {
      values: { ...BASE, quietStart: "23:00" },
      version: 2,
      updatedAt: "2026-11-12T13:02:00Z",
      updatedVia,
    },
  };
}

function renderLayer(updatedVia: "web" | "telegram" | null): HTMLElement {
  const { container } = render(<ConflictLayer conflict={conflictVia(updatedVia)} setValue={vi.fn()} values={MINE} />);
  return container;
}

describe("conflict marks name where the other change came from", () => {
  it("given the other change came from the web, when the marks render, then they say the web has the value and the button keeps the stored value", () => {
    renderLayer("web");

    expect(screen.getByText("You typed 22:30, the web now has 23:00")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep the stored value for Quiet hours from" })).toHaveTextContent(
      "Keep the stored value",
    );
    expect(screen.getByRole("button", { name: "Use mine for Quiet hours from" })).toBeInTheDocument();
    expect(screen.queryByText(/Telegram/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Telegram/ })).not.toBeInTheDocument();
  });

  it("given the other change came from Telegram, when the marks render, then the wording names Telegram", () => {
    renderLayer("telegram");

    expect(screen.getByText("You typed 22:30, Telegram now has 23:00")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep Telegram's for Quiet hours from" })).toHaveTextContent(
      "Keep Telegram's",
    );
  });

  it.each(["web", "telegram"] as const)("given a change via %s, when axe runs, then there is no violation", async (via) => {
    const container = renderLayer(via);

    await expectNoAxeViolations(container);
  });
});
