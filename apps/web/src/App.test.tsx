import { render, screen } from "@testing-library/react";

import { App } from "@/App";
import { expectNoAxeViolations } from "@/test/axe";

describe("App", () => {
  it("given the app, when rendered, then shows the project name as the main heading", () => {
    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "Mail Assistant" })).toBeInTheDocument();
  });

  it("given the app, when rendered, then content sits in a main landmark", () => {
    render(<App />);

    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("given the app, when rendered, then has no accessibility violations", async () => {
    const { container } = render(<App />);

    await expectNoAxeViolations(container);
  });
});
