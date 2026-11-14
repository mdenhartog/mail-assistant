import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { Layout } from "@/components/Layout";
import type { LayoutAccount } from "@/components/Layout";
import { expectNoAxeViolations } from "@/test/axe";
import { expectMotionOnlyWhenSafe } from "@/test/motion";

function account(extra: Partial<LayoutAccount> = {}): LayoutAccount {
  return { maskedAddress: "m***@example.com", onSignOut: vi.fn(), ...extra };
}

describe("Layout", () => {
  it("given the page, when tabbing once, then the skip link is first and Enter moves focus to main", async () => {
    render(
      <Layout account={account()}>
        <h1>Settings</h1>
      </Layout>,
    );
    await userEvent.tab();
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(screen.getByRole("main")).toHaveFocus();
  });

  it("given the page, when rendered, then there is one banner and one main holding the children", () => {
    render(
      <Layout account={account()}>
        <h1>Settings</h1>
      </Layout>,
    );
    expect(screen.getAllByRole("banner")).toHaveLength(1);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("main")).toContainElement(screen.getByRole("heading", { name: "Settings" }));
    expect(screen.getByRole("banner")).toHaveTextContent("Mail Assistant");
  });

  it("given an account, when rendered, then the masked address and Sign out are in the header", async () => {
    const onSignOut = vi.fn();
    render(
      <Layout account={account({ onSignOut })}>
        <p>x</p>
      </Layout>,
    );
    expect(screen.getByRole("banner")).toHaveTextContent("Signed in as m***@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });

  it("given signing out, when pressed again, then the handler is not called twice", async () => {
    const onSignOut = vi.fn();
    const { rerender } = render(
      <Layout account={account({ onSignOut })}>
        <p>x</p>
      </Layout>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    rerender(
      <Layout account={account({ onSignOut, signingOut: true })}>
        <p>x</p>
      </Layout>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Signing out..." }));
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });

  it("given a failed sign out, when rendered, then an alert says so", () => {
    render(
      <Layout account={account({ signOutFailed: true })}>
        <p>x</p>
      </Layout>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Could not sign out. Try again.");
  });

  it("given no account, when rendered, then there is no Sign out and no address", () => {
    render(
      <Layout>
        <p>x</p>
      </Layout>,
    );
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Signed in as/)).not.toBeInTheDocument();
  });

  it("given a reduced-motion preference, when rendered, then the skip link sets no bare motion", () => {
    render(
      <Layout>
        <p>x</p>
      </Layout>,
    );
    expectMotionOnlyWhenSafe(screen.getByRole("link", { name: "Skip to main content" }));
  });

  it("given the layout with and without account, when axe runs, then there is no violation", async () => {
    const a = render(
      <Layout account={account({ signOutFailed: true })}>
        <h1>Settings</h1>
      </Layout>,
    );
    await expectNoAxeViolations(a.container);
    a.unmount();
    const b = render(
      <Layout>
        <h1>Sign in</h1>
      </Layout>,
    );
    await expectNoAxeViolations(b.container);
  });
});
