import type { ReactElement } from "react";
import { Link } from "react-router";

import { usePageTitle } from "@/pages/usePageTitle";
import { paths } from "@/router/paths";

export function NotFound(): ReactElement {
  usePageTitle("Page not found");
  return (
    <main className="mx-auto max-w-xl px-6 py-12">
      <h1 className="font-display text-2xl text-text">Page not found</h1>
      <p className="mt-3 text-text-muted">There is nothing at this address.</p>
      <Link className="mt-6 inline-flex min-h-11 items-center text-primary underline" to={paths.settings}>
        Back to settings
      </Link>
    </main>
  );
}
