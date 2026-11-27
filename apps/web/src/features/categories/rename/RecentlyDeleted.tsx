import type { ReactElement } from "react";

import { useDeletedLabels } from "@/api/categories/rename.queries";
import type { DeletedLabels } from "@/api/categories/rename.types";
import { Banner } from "@/components/Banner";
import { DELETED } from "@/features/categories/rename/copy";

const DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });

function newestFirst(items: DeletedLabels["items"]): DeletedLabels["items"] {
  return [...items].sort((a, b) => Date.parse(b.deletedAt) - Date.parse(a.deletedAt));
}

function Loading(): ReactElement {
  return (
    <div aria-busy="true">
      <p className="text-text-muted" role="status">
        {DELETED.loading}
      </p>
      <div aria-hidden="true" className="mt-3 h-11 w-full rounded-control bg-divider motion-safe:animate-pulse" data-skeleton="" />
    </div>
  );
}

function Entries({ data }: { data: DeletedLabels }): ReactElement {
  if (data.items.length === 0) {
    return <p className="text-text-muted">{DELETED.empty(data.retentionDays)}</p>;
  }
  return (
    <ul className="flex flex-col gap-2">
      {newestFirst(data.items).map((entry) => (
        <li className="flex flex-col gap-1 rounded-control bg-surface-raised px-4 py-3 sm:flex-row sm:justify-between" key={`${entry.deletedAt}-${entry.name}`}>
          <span className="min-w-0 font-semibold text-text wrap-anywhere">{entry.name}</span>
          <span className="text-sm text-text-muted">
            {DELETED.deletedOn} <time dateTime={entry.deletedAt}>{DATE.format(new Date(entry.deletedAt))}</time>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** The labels the assistant deleted within the retention period: names and dates, newest first, read-only. */
export function RecentlyDeleted(): ReactElement {
  const deleted = useDeletedLabels();
  let content: ReactElement;
  if (deleted.isPending) {
    content = <Loading />;
  } else if (deleted.isError) {
    content = (
      <Banner
        action={{
          label: "Try again",
          onClick: () => {
            void deleted.refetch();
          },
        }}
        kind="danger"
        title={DELETED.loadFailed}
      >
        Check your connection and try again.
      </Banner>
    );
  } else {
    content = (
      <>
        <p className="text-text">{DELETED.intro(deleted.data.retentionDays)}</p>
        <Entries data={deleted.data} />
      </>
    );
  }
  return (
    <section aria-labelledby="recently-deleted" className="mt-10 flex flex-col gap-4 border-t border-divider pt-8">
      <h2 className="font-display text-xl text-text wrap-anywhere" id="recently-deleted">
        {DELETED.title}
      </h2>
      {content}
    </section>
  );
}
