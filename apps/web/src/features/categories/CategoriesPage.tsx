import type { ReactElement } from "react";

import { useCategories } from "@/api/categories/categories.queries";
import { ApiError } from "@/api/client";
import { Banner } from "@/components/Banner";
import { CategoriesForm } from "@/features/categories/CategoriesForm";
import { usePageTitle } from "@/pages/usePageTitle";

function Loading(): ReactElement {
  return (
    <div aria-busy="true" className="mt-6">
      <p className="text-text-muted">Loading your categories</p>
      <div aria-hidden="true" className="mt-4 grid gap-4 sm:grid-cols-2">
        {[0, 1, 2, 3].map((row) => (
          <div className="h-40 rounded-card bg-divider motion-safe:animate-pulse" data-skeleton="" key={row} />
        ))}
      </div>
    </div>
  );
}

function LoadFailed({ error, onRetry }: { error: unknown; onRetry: () => void }): ReactElement {
  const tooMany = error instanceof ApiError && error.status === 429;
  return (
    <div className="mt-6">
      <Banner
        action={{ label: "Try again", onClick: onRetry }}
        kind="danger"
        title={tooMany ? "Too many requests." : "Could not load your categories."}
      >
        {tooMany ? "Wait a minute and try again." : "Check your connection and try again."}
      </Banner>
    </div>
  );
}

/** `/categories`: loads the stored list, then shows the form. */
export function CategoriesPage(): ReactElement {
  usePageTitle("Categories");
  const { data, isPending, isError, error, refetch } = useCategories();
  let content: ReactElement;
  if (isPending) {
    content = <Loading />;
  } else if (isError) {
    content = (
      <LoadFailed
        error={error}
        onRetry={() => {
          void refetch();
        }}
      />
    );
  } else if (!data.ready) {
    content = (
      <div className="mt-6">
        <Banner kind="info" title="Your categories are not ready yet.">
          The assistant is still setting them up. Try again in a few minutes.
        </Banner>
      </div>
    );
  } else {
    content = <CategoriesForm list={data} />;
  }
  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="font-display text-2xl text-text">Categories</h1>
      {content}
    </div>
  );
}
