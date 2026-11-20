import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StickyBar } from "@/components/StickyBar";

function barHeight(height: number, windowHeight: number): void {
  vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(height);
  vi.stubGlobal("innerHeight", windowHeight);
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.documentElement.style.removeProperty("scroll-padding-bottom");
});

describe("StickyBar", () => {
  it("shows what it is given and is marked as the action bar of the page", () => {
    render(<StickyBar>Save here</StickyBar>);

    expect(screen.getByText("Save here")).toHaveAttribute("data-action-bar");
  });

  it("sticks to the bottom and keeps scrolling clear of itself while it takes up to a third of the window", () => {
    barHeight(160, 600);
    render(<StickyBar>Save here</StickyBar>);

    expect(screen.getByText("Save here")).toHaveAttribute("data-sticky", "true");
    expect(document.documentElement.style.getPropertyValue("scroll-padding-bottom")).toBe("168px");
  });

  it("falls back into the flow of the page when it would take more than a third of the window", () => {
    barHeight(300, 600);
    render(<StickyBar>Save here</StickyBar>);

    expect(screen.getByText("Save here")).not.toHaveAttribute("data-sticky");
    expect(document.documentElement.style.getPropertyValue("scroll-padding-bottom")).toBe("");
  });

  it("gives the scroll padding back when it goes away", () => {
    barHeight(160, 600);
    const { unmount } = render(<StickyBar>Save here</StickyBar>);

    unmount();

    expect(document.documentElement.style.getPropertyValue("scroll-padding-bottom")).toBe("");
  });
});
