import { render, screen } from "@testing-library/react";

import { Field } from "@/components/Field";
import { expectNoAxeViolations } from "@/test/axe";

function renderField(props: { hint?: string; error?: string }): ReturnType<typeof render> {
  return render(
    <Field label="Time zone" {...props}>
      {(control) => <input {...control} />}
    </Field>,
  );
}

describe("Field", () => {
  it("given a hint and an error, when rendered, then label, hint and error are all linked", () => {
    renderField({ hint: "Type a city.", error: "Pick a place from the list." });
    const input = screen.getByLabelText("Time zone");
    const hint = screen.getByText("Type a city.");
    const error = screen.getByRole("alert");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input.getAttribute("aria-describedby")?.split(" ")).toEqual([hint.id, error.id]);
    expect(error).toHaveTextContent("Pick a place from the list.");
    expect(error).toHaveTextContent("!");
  });

  it("given a hint only, when rendered, then aria-invalid is absent and no alert exists", () => {
    renderField({ hint: "Type a city." });
    const input = screen.getByLabelText("Time zone");
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input).toHaveAccessibleDescription("Type a city.");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("given neither hint nor error, when rendered, then there is no aria-describedby", () => {
    renderField({});
    expect(screen.getByLabelText("Time zone")).not.toHaveAttribute("aria-describedby");
  });

  it("given two fields, when rendered, then their ids differ", () => {
    render(
      <>
        <Field label="From">{(control) => <input {...control} />}</Field>
        <Field label="Until">{(control) => <input {...control} />}</Field>
      </>,
    );
    expect(screen.getByLabelText("From").id).not.toBe(screen.getByLabelText("Until").id);
  });

  it("given the field with hint and error, when axe runs, then there is no violation", async () => {
    const { container } = renderField({ hint: "Type a city.", error: "Pick a place from the list." });
    await expectNoAxeViolations(container);
  });
});
