import type { ReactElement } from "react";

import { usePageTitle } from "@/pages/usePageTitle";

/** Placeholder until the sign-in steps arrive (U-web-settings-30). */
export function LoginPage(): ReactElement {
  usePageTitle("Sign in");
  return (
    <main className="mx-auto max-w-xl px-6 py-12">
      <h1 className="font-display text-2xl text-text">Sign in</h1>
    </main>
  );
}
