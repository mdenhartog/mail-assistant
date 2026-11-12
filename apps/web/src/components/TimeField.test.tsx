import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { Field } from "@/components/Field";
import { TimeField } from "@/components/TimeField";
import { expectNoAxeViolations } from "@/test/axe";
import { expectMotionOnlyWhenSafe } from "@/test/motion";

interface Options {
  native?: boolean;
  readOnly?: boolean;
  onChange?: (value: string) => void;
}

function renderTime(value: string, options: Options = {}): ReturnType<typeof render> {
  const { onChange = vi.fn(), ...rest } = options;
  return render(
    <Field label="From">{(control) => <TimeField {...control} {...rest} onChange={onChange} value={value} />}</Field>,
  );
}

describe("TimeField", () => {
  it("given a stored 22:10, when rendered natively, then the value is unchanged with a 24-hour echo", () => {
    renderTime("22:10", { native: true });
    const input = screen.getByLabelText("From");
    expect(input).toHaveAttribute("type", "time");
    expect(input).toHaveAttribute("step", "60");
    expect(input).toHaveValue("22:10");
    expect(screen.getByText("= 22:10")).toBeInTheDocument();
  });

  it("given a native change, when the user types, then onChange gets the new value", async () => {
    const onChange = vi.fn();
    renderTime("22:10", { native: true, onChange });
    const input = screen.getByLabelText("From");
    await userEvent.clear(input);
    await userEvent.type(input, "23:15");
    expect(onChange).toHaveBeenCalled();
  });

  it("given the select fallback, when stored 22:10 is off the grid, then 15-minute values plus 22:10 are offered", () => {
    renderTime("22:10", { native: false });
    const select = screen.getByLabelText("From");
    expect(select.tagName).toBe("SELECT");
    const values = screen.getAllByRole("option").map((o) => o.getAttribute("value"));
    expect(values).toHaveLength(97);
    expect(values).toContain("22:00");
    expect(values).toContain("22:15");
    expect(values.indexOf("22:10")).toBeGreaterThan(values.indexOf("22:00"));
    expect(values.indexOf("22:10")).toBeLessThan(values.indexOf("22:15"));
    expect(select).toHaveValue("22:10");
    expect(screen.getByText("= 22:10")).toBeInTheDocument();
  });

  it("given the select fallback on the grid, when rendered, then exactly 96 options", () => {
    renderTime("07:30", { native: false });
    expect(screen.getAllByRole("option")).toHaveLength(96);
  });

  it("given the select fallback, when the user picks a value, then onChange gets it", async () => {
    const onChange = vi.fn();
    renderTime("22:00", { native: false, onChange });
    await userEvent.selectOptions(screen.getByLabelText("From"), "23:45");
    expect(onChange).toHaveBeenCalledWith("23:45");
  });

  it("given read-only, when the user changes the select, then onChange is not called", async () => {
    const onChange = vi.fn();
    renderTime("22:00", { native: false, readOnly: true, onChange });
    expect(screen.getByLabelText("From")).toHaveAttribute("aria-readonly", "true");
    await userEvent.selectOptions(screen.getByLabelText("From"), "23:45");
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByLabelText("From")).toHaveValue("22:00");
  });

  it("given read-only, when rendered natively, then the input is readonly", () => {
    renderTime("22:00", { native: true, readOnly: true });
    expect(screen.getByLabelText("From")).toHaveAttribute("readonly");
  });

  it("given no override, when jsdom supports type=time, then the native control is used", () => {
    renderTime("07:00");
    expect(screen.getByLabelText("From")).toHaveAttribute("type", "time");
  });

  it("given a browser without type=time, when detected, then the select is used", () => {
    const spy = vi.spyOn(HTMLInputElement.prototype, "type", "get").mockReturnValue("text");
    try {
      renderTime("07:00");
    } finally {
      spy.mockRestore();
    }
    expect(screen.getByLabelText("From").tagName).toBe("SELECT");
  });

  it("given both variants, when axe runs, then there is no violation", async () => {
    const a = renderTime("22:10", { native: true });
    await expectNoAxeViolations(a.container);
    a.unmount();
    const b = renderTime("22:10", { native: false });
    await expectNoAxeViolations(b.container);
  });

  it("given a reduced-motion preference, when rendered, then no motion applies outside motion-safe", () => {
    renderTime("22:10", { native: true });
    expectMotionOnlyWhenSafe(screen.getByLabelText("From"));
  });
});
