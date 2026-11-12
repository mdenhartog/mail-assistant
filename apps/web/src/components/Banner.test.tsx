import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { Banner } from "@/components/Banner";
import type { BannerKind } from "@/components/Banner";
import { expectNoAxeViolations } from "@/test/axe";
import { expectMotionOnlyWhenSafe } from "@/test/motion";

const KINDS: [BannerKind, string, string][] = [
  ["danger", "alert", "!"],
  ["conflict", "alert", "!"],
  ["success", "status", "✓"],
  ["info", "status", "i"],
];

describe("Banner", () => {
  it.each(KINDS)("given kind %s, when rendered, then role %s, a title and the marker %s", (kind, role, mark) => {
    render(
      <Banner kind={kind} title="Heads up.">
        Something happened.
      </Banner>,
    );
    const banner = screen.getByRole(role);
    expect(banner).toHaveTextContent("Heads up. Something happened.");
    expect(banner.querySelector("strong")).toHaveTextContent("Heads up.");
    const icon = banner.querySelector("[data-banner-icon]");
    expect(icon).toHaveTextContent(mark);
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it.each(KINDS)("given kind %s, when rendered, then the icon circle and its mark use different colours", (kind, role) => {
    render(<Banner kind={kind} title="T" />);
    const icon = screen.getByRole(role).querySelector("[data-banner-icon]");
    const classes = (icon?.className ?? "").split(/\s+/);
    const background = classes.find((c) => c.startsWith("bg-"));
    const foreground = classes.find((c) => c.startsWith("text-") && c !== "text-sm");
    expect(background).toBeDefined();
    expect(foreground).toBeDefined();
    expect(background?.slice("bg-".length)).not.toBe(foreground?.slice("text-".length));
    expect(classes).not.toContain("text-current");
    expect(classes).not.toContain("bg-current");
  });

  it("given the same props, when re-rendered, then the live region node is kept", () => {
    const { rerender } = render(
      <Banner kind="success" title="Saved.">
        Quiet hours are 23:00 to 07:00.
      </Banner>,
    );
    const before = screen.getByRole("status");
    rerender(
      <Banner kind="success" title="Saved.">
        Quiet hours are 23:00 to 07:00.
      </Banner>,
    );
    expect(screen.getByRole("status")).toBe(before);
  });

  it("given an action, when pressed, then its handler runs", async () => {
    const onClick = vi.fn();
    render(<Banner action={{ label: "Try again", onClick }} kind="danger" title="Could not save." />);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("given focusOnMount, when rendered, then the banner has focus", () => {
    render(<Banner focusOnMount kind="conflict" title="Settings changed." />);
    expect(screen.getByRole("alert")).toHaveFocus();
  });

  it("given no focusOnMount, when rendered, then focus is left alone and the banner is not a tab stop", () => {
    render(<Banner kind="info" title="FYI." />);
    expect(screen.getByRole("status")).not.toHaveFocus();
    expect(screen.getByRole("status")).not.toHaveAttribute("tabindex");
  });

  it("given a reduced-motion preference, when rendered, then the enter animation is motion-safe only", () => {
    render(<Banner kind="info" title="FYI." />);
    expectMotionOnlyWhenSafe(screen.getByRole("status"));
    expect(screen.getByRole("status").className).toContain("motion-safe:");
  });

  it("given every kind, when axe runs, then there is no violation", async () => {
    const { container } = render(
      <div>
        {KINDS.map(([kind]) => (
          <Banner action={{ label: "Act", onClick: vi.fn() }} key={kind} kind={kind} title="Title.">
            Text.
          </Banner>
        ))}
      </div>,
    );
    await expectNoAxeViolations(container);
  });
});
