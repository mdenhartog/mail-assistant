import { render, screen } from "@testing-library/react";

import { FieldGroup } from "@/components/FieldGroup";
import { expectNoAxeViolations } from "@/test/axe";

function renderGroup(error?: string): HTMLElement {
  return render(
    <FieldGroup error={error} hint="Alerts wait until it ends." legend="Quiet hours">
      {(control) => (
        <>
          <input {...control} aria-label="From" />
          <input {...control} aria-label="Until" />
        </>
      )}
    </FieldGroup>,
  ).container;
}

describe("FieldGroup", () => {
  it("given a legend and a hint, when rendered, then the group is named and every control is described by the hint", () => {
    renderGroup();

    expect(screen.getByRole("group", { name: "Quiet hours" })).toBeInTheDocument();
    for (const name of ["From", "Until"]) {
      expect(screen.getByLabelText(name)).toHaveAccessibleDescription("Alerts wait until it ends.");
      expect(screen.getByLabelText(name)).not.toHaveAttribute("aria-invalid");
    }
  });

  it("given an error, when rendered, then it is an alert with a mark and every control is invalid and described by hint plus error", async () => {
    const container = renderGroup("Quiet hours can be 1 to 12 hours.");

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("!");
    expect(alert).toHaveTextContent("Quiet hours can be 1 to 12 hours.");
    for (const name of ["From", "Until"]) {
      expect(screen.getByLabelText(name)).toHaveAttribute("aria-invalid", "true");
      expect(screen.getByLabelText(name)).toHaveAccessibleDescription(
        "Alerts wait until it ends. Quiet hours can be 1 to 12 hours.",
      );
    }
    await expectNoAxeViolations(container);
  });

  it("given no error, when rendered, then there is no alert", async () => {
    const container = renderGroup();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await expectNoAxeViolations(container);
  });
});
