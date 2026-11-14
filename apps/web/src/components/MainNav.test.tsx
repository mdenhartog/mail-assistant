import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { MainNav } from "@/components/MainNav";
import { expectNoAxeViolations } from "@/test/axe";

function setup(at: string, openItems?: number): ReturnType<typeof render> {
  return render(
    <MemoryRouter initialEntries={[at]}>
      <MainNav openItems={openItems} />
    </MemoryRouter>,
  );
}

describe("MainNav", () => {
  it("given the settings page, when rendered, then a navigation landmark has the three links and marks the current one", () => {
    setup("/settings", 842);
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(nav).toContainElement(screen.getByRole("link", { name: "Settings" }));
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Categories" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: /^Review moves/ })).not.toHaveAttribute("aria-current");
  });

  it("given 842 open items, when rendered, then the review link carries the badge text '842 open items'", () => {
    setup("/review", 842);
    const link = screen.getByRole("link", { name: /Review moves/ });
    expect(link).toHaveAccessibleName("Review moves 842 open items");
    expect(link).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("842")).toHaveAttribute("aria-hidden", "true");
  });

  it.each([[0], [undefined]])("given %s open items, when rendered, then there is no badge", (count) => {
    setup("/categories", count);
    expect(screen.queryByText(/open items/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review moves" })).toBeInTheDocument();
  });

  it("given the nav, when axe runs, then there is no violation", async () => {
    const { container } = setup("/settings", 842);
    await expectNoAxeViolations(container);
  });
});
