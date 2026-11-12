import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { Button } from "@/components/Button";
import { expectNoAxeViolations } from "@/test/axe";
import { expectMotionOnlyWhenSafe } from "@/test/motion";

describe("Button", () => {
  it("given loading, when clicked again, then the handler ran once in total and the label changed", async () => {
    const onClick = vi.fn();
    const { rerender } = render(<Button onClick={onClick}>Save changes</Button>);
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    rerender(
      <Button loading onClick={onClick}>
        Save changes
      </Button>,
    );
    const busy = screen.getByRole("button", { name: "Saving..." });
    expect(busy).toHaveAttribute("aria-disabled", "true");
    expect(busy).toHaveAttribute("aria-busy", "true");
    expect(busy).not.toBeDisabled();
    await userEvent.click(busy);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("given loading with its own label, when rendered, then that label shows", () => {
    render(
      <Button loading loadingLabel="Sending...">
        Send me a code
      </Button>,
    );
    expect(screen.getByRole("button", { name: "Sending..." })).toBeInTheDocument();
  });

  it("given disabled, when clicked, then nothing happens", async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Save changes
      </Button>,
    );
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).not.toHaveBeenCalled();
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("given no type, when rendered, then it is a plain button that does not submit", () => {
    render(<Button>Go</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });

  it("given a reduced-motion preference, when rendered, then no motion applies outside motion-safe", () => {
    render(<Button variant="primary">Go</Button>);
    expectMotionOnlyWhenSafe(screen.getByRole("button"));
    expect(screen.getByRole("button").className).toContain("motion-safe:");
  });

  it("given every variant and state, when axe runs, then there is no violation", async () => {
    const { container } = render(
      <div>
        <Button variant="primary">Primary</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="danger">Danger</Button>
        <Button disabled>Off</Button>
        <Button loading>Busy</Button>
      </div>,
    );
    await expectNoAxeViolations(container);
  });
});
