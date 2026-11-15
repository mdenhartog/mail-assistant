import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ActionBar } from "@/features/review/ActionBar";

function barHeight(height: number, windowHeight: number): void {
  vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(height);
  vi.stubGlobal("innerHeight", windowHeight);
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.documentElement.style.removeProperty("scroll-padding-bottom");
});

describe("ActionBar", () => {
  it("says what the button does and how many mails stay where they are", () => {
    render(<ActionBar approved={12} onMove={() => undefined} undecided={30} />);

    expect(screen.getByRole("button", { name: "Move 12 mails, labels only" })).toBeEnabled();
    expect(screen.getByText("30 not decided yet stay where they are.")).toBeInTheDocument();
  });

  it("with nothing approved the button is disabled and the text says what to do first", async () => {
    const onMove = vi.fn();
    render(<ActionBar approved={0} onMove={onMove} undecided={30} />);

    const button = screen.getByRole("button", { name: "Move 0 mails, labels only" });
    await userEvent.click(button);

    expect(button).toBeDisabled();
    expect(onMove).not.toHaveBeenCalled();
    expect(screen.getByText(/Approve a group or tick mails first/)).toBeInTheDocument();
  });

  it("sticks to the bottom and keeps scrolling clear of itself while it takes up to a third of the window", () => {
    barHeight(160, 640);
    const { container } = render(<ActionBar approved={1} onMove={() => undefined} undecided={0} />);

    expect(container.querySelector("[data-action-bar]")).toHaveAttribute("data-sticky", "true");
    expect(document.documentElement.style.getPropertyValue("scroll-padding-bottom")).toBe("160px");
  });

  it("falls back into the flow of the page when it would take more than a third of the window (large text, small window)", () => {
    barHeight(400, 640);
    const { container } = render(<ActionBar approved={1} onMove={() => undefined} undecided={0} />);

    expect(container.querySelector("[data-action-bar]")).not.toHaveAttribute("data-sticky");
    expect(document.documentElement.style.getPropertyValue("scroll-padding-bottom")).toBe("");
  });

  it("gives the scroll padding back when it goes away", () => {
    barHeight(160, 640);
    const { unmount } = render(<ActionBar approved={1} onMove={() => undefined} undecided={0} />);
    unmount();

    expect(document.documentElement.style.getPropertyValue("scroll-padding-bottom")).toBe("");
  });
});
