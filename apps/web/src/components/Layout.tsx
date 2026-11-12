import { useRef } from "react";
import type { MouseEvent, ReactElement, ReactNode } from "react";

import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";

export interface LayoutAccount {
  maskedAddress: string;
  onSignOut: () => void;
  signingOut?: boolean;
  signOutFailed?: boolean;
}

export interface LayoutProps {
  /** Present on pages that need a session; public pages leave it out. */
  account?: LayoutAccount;
  children: ReactNode;
}

/**
 * Page frame: skip link first, header with the brand (and the masked address and Sign out when
 * signed in), then the single `main` landmark that holds the page.
 *
 * @example
 * <Layout account={{ maskedAddress: "m***@example.com", onSignOut }}><h1>Settings</h1></Layout>
 */
export function Layout({ account, children }: LayoutProps): ReactElement {
  const mainRef = useRef<HTMLElement>(null);
  const skip = (event: MouseEvent<HTMLAnchorElement>): void => {
    event.preventDefault();
    mainRef.current?.focus();
  };
  return (
    <div className="min-h-dvh">
      <a
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-10 focus:inline-flex focus:min-h-11 focus:items-center focus:rounded-control focus:border-2 focus:border-primary focus:bg-surface-raised focus:px-4 focus:text-text"
        href="#main"
        onClick={skip}
      >
        Skip to main content
      </a>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-divider px-6 py-4">
        <span className="font-display text-lg text-text">Mail Assistant</span>
        {account ? (
          <>
            <p className="text-sm text-text-muted">Signed in as {account.maskedAddress}</p>
            <Button loading={account.signingOut ?? false} loadingLabel="Signing out..." onClick={account.onSignOut}>
              Sign out
            </Button>
          </>
        ) : null}
      </header>
      {account?.signOutFailed ? (
        <div className="px-6 pt-4">
          <Banner kind="danger" title="Could not sign out.">
            Try again.
          </Banner>
        </div>
      ) : null}
      <main className="focus:outline-none" id="main" ref={mainRef} tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
