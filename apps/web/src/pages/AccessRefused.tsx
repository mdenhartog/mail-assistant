import type { ReactElement } from "react";
import { Link } from "react-router";

import { usePageTitle } from "@/pages/usePageTitle";
import { paths } from "@/router/paths";

interface AccessRefusedProps {
  onBack: () => void;
}

/** Full-page refusal for a 403. It replaces the whole app, so no settings data stays in the DOM. */
export function AccessRefused({ onBack }: AccessRefusedProps): ReactElement {
  usePageTitle("Not allowed");
  return (
    <main className="mx-auto max-w-xl px-6 py-12">
      <h1 className="font-display text-2xl text-text">Access refused</h1>
      <p className="mt-3 text-text">This request was not allowed.</p>
      <Link
        className="mt-6 inline-flex min-h-11 items-center rounded-full bg-primary px-5 text-primary-contrast"
        onClick={onBack}
        to={paths.login}
      >
        Back to sign in
      </Link>
    </main>
  );
}
