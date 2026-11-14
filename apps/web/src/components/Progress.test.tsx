import { render, screen } from "@testing-library/react";

import { Progress } from "@/components/Progress";
import { expectNoAxeViolations } from "@/test/axe";

describe("Progress", () => {
  it("given 340 of 2000, when rendered, then the progressbar carries the numbers and the value text", () => {
    render(<Progress label="Mails sorted" max={2000} value={340} />);
    const bar = screen.getByRole("progressbar", { name: "Mails sorted" });
    expect(bar).toHaveAttribute("aria-valuenow", "340");
    expect(bar).toHaveAttribute("aria-valuemax", "2000");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuetext", "340 of 2000");
  });

  it("given 340 of 2000, when rendered, then the fill is 17 percent wide", () => {
    render(<Progress label="Mails sorted" max={2000} value={340} />);
    expect(screen.getByRole("progressbar").firstElementChild).toHaveStyle({ width: "17%" });
  });

  it.each([
    [-5, 100, "0"],
    [150, 100, "100"],
  ])("given value %s of %s, when rendered, then it is clamped to %s", (value, max, expected) => {
    render(<Progress label="x" max={max} value={value} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", expected);
  });

  it("given max 0 (nothing to do), when rendered, then the bar is empty and valid", () => {
    render(<Progress label="x" max={0} value={0} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "0 of 0");
  });

  it("given a bar, when axe runs, then there is no violation", async () => {
    const { container } = render(<Progress label="Mails sorted" max={2000} value={340} />);
    await expectNoAxeViolations(container);
  });
});
