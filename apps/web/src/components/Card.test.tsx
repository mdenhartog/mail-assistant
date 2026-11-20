import { render, screen } from "@testing-library/react";

import { Card } from "@/components/Card";
import { expectNoAxeViolations } from "@/test/axe";

describe("Card", () => {
  it("given children, when rendered, then they sit in the raised card surface", () => {
    render(
      <Card>
        <p>Inside</p>
      </Card>,
    );
    expect(screen.getByText("Inside").parentElement).toHaveClass("rounded-card", "bg-surface-raised", "p-5", "shadow-soft");
  });

  it("given a card, when axe runs, then there is no violation", async () => {
    const { container } = render(
      <Card>
        <p>Inside</p>
      </Card>,
    );
    await expectNoAxeViolations(container);
  });
});
