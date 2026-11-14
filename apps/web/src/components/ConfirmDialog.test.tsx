import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import type { ConfirmTone } from "@/components/ConfirmDialog";
import { expectNoAxeViolations } from "@/test/axe";

function setup(tone: ConfirmTone, body: React.ReactNode = <p>It renames labels.</p>) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const view = render(
    <ConfirmDialog cancelLabel="Keep" confirmLabel="Save" onCancel={onCancel} onConfirm={onConfirm} open title="Save?" tone={tone}>
      {body}
    </ConfirmDialog>,
  );
  return { onConfirm, onCancel, ...view };
}

describe("ConfirmDialog", () => {
  it("given tone safe, when it opens, then cancel comes first with the focus and confirm is primary (AC-55)", () => {
    setup("safe");
    const buttons = screen.getAllByRole("button");
    expect(buttons[0]).toHaveAccessibleName("Keep");
    expect(buttons[0]).toHaveFocus();
    expect(screen.getByRole("button", { name: "Save" })).toHaveClass("bg-primary");
    expect(screen.getByRole("button", { name: "Save" })).not.toHaveClass("bg-danger");
  });

  it("given tone danger, when it opens, then confirm keeps the red style and cancel has the focus", () => {
    setup("danger");
    expect(screen.getByRole("button", { name: "Save" })).toHaveClass("bg-danger");
    expect(screen.getByRole("button", { name: "Keep" })).toHaveFocus();
  });

  it.each<ConfirmTone>(["safe", "danger"])(
    "given tone %s and a link and a checkbox in the body, when Tab and Shift+Tab are pressed, then focus turns round over every focusable element (AC-55)",
    async (tone) => {
      setup(
        tone,
        <p>
          <a href="/help">Help</a> <input aria-label="Do not ask again" type="checkbox" />
        </p>,
      );
      // DOM order: Help, checkbox, Keep, Save; the focus starts on Keep.
      const names = (): string | null => document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.textContent ?? null;
      expect(names()).toBe("Keep");
      for (const expected of ["Save", "Help", "Do not ask again", "Keep"]) {
        await userEvent.tab();
        expect(names()).toBe(expected);
      }
      await userEvent.tab({ shift: true });
      expect(names()).toBe("Do not ask again");
      await userEvent.tab({ shift: true });
      expect(names()).toBe("Help");
      await userEvent.tab({ shift: true });
      expect(names()).toBe("Save");
    },
  );

  it("given the dialog, when Escape is pressed, then it cancels and never confirms", async () => {
    const { onCancel, onConfirm } = setup("safe");
    await userEvent.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("given the dialog, when confirm is pressed, then only onConfirm runs", async () => {
    const { onCancel, onConfirm } = setup("danger");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("given open is false, when rendered, then nothing is shown", () => {
    render(
      <ConfirmDialog cancelLabel="a" confirmLabel="b" onCancel={vi.fn()} onConfirm={vi.fn()} open={false} title="t" tone="safe">
        x
      </ConfirmDialog>,
    );
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it.each<ConfirmTone>(["safe", "danger"])("given tone %s, when axe runs, then there is no violation", async (tone) => {
    const { baseElement } = setup(tone);
    await expectNoAxeViolations(baseElement);
  });
});
