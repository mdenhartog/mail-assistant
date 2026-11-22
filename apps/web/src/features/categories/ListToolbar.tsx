import { useId } from "react";
import type { ReactElement } from "react";

import type { ListView } from "@/features/categories/useListView";

/** The search field and the filter "Always notify only"; `shown` is the number of matches while a filter is on. */
export function ListToolbar({ view, shown }: { view: ListView; shown: number | null }): ReactElement {
  const id = useId();
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <label className="font-semibold text-text" htmlFor={id}>
          Search categories
        </label>
        <input
          autoComplete="off"
          className="min-h-11 w-full min-w-0 rounded-control border border-border bg-surface-raised px-3 py-2 text-text"
          id={id}
          onChange={(event) => {
            view.setQuery(event.target.value);
          }}
          type="search"
          value={view.filter.query}
        />
      </div>
      <label className="flex min-h-11 cursor-pointer items-center gap-3 text-text">
        <input
          checked={view.filter.notifyOnly}
          className="size-11 cursor-pointer"
          onChange={(event) => {
            view.setNotifyOnly(event.target.checked);
          }}
          type="checkbox"
        />
        Always notify only
      </label>
      {shown === null ? null : (
        <p className="text-sm text-text-muted" role="status">
          {shown === 0 ? "No category matches." : `${String(shown)} ${shown === 1 ? "category matches" : "categories match"}.`}
        </p>
      )}
    </div>
  );
}
