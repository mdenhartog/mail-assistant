import { useCallback, useState } from "react";
import type { ReactElement } from "react";

import { usePlanItems } from "@/api/plan/plan.queries";
import type { Decision, PlanGroup, PlanItem } from "@/api/plan/plan.types";
import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { ReviewItem } from "@/features/review/ReviewItem";
import { groupKey } from "@/features/review/text";

/** Pages are 100 items and the API allows 100 pages; the loop never runs longer than that. */
const MAX_PAGES = 100;

export type SelectionUpdate = (previous: ReadonlySet<number>) => ReadonlySet<number>;

export interface GroupPanelProps {
  group: PlanGroup;
  title: string;
  selected: ReadonlySet<number>;
  busy: boolean;
  onSelection: (key: string, update: SelectionUpdate) => void;
  onDecideSelected: (group: PlanGroup, decision: Decision, ids: number[]) => void;
}

function toggled(id: number): SelectionUpdate {
  return (previous) => {
    const next = new Set(previous);
    if (!next.delete(id)) {
      next.add(id);
    }
    return next;
  };
}

function Skeleton(): ReactElement {
  return (
    <div aria-busy="true" className="mt-3">
      <p className="text-text-muted">Loading these mails</p>
      <div aria-hidden="true" className="mt-3 grid gap-2">
        {[0, 1, 2].map((row) => (
          <div className="h-12 rounded-control bg-divider motion-safe:animate-pulse" data-skeleton="" key={row} />
        ))}
      </div>
    </div>
  );
}

interface ToolsProps {
  group: PlanGroup;
  selected: ReadonlySet<number>;
  busy: boolean;
  selecting: boolean;
  onSelectAll: () => void;
  onClear: () => void;
  onDecide: (decision: Decision) => void;
}

function Tools({ group, selected, busy, selecting, onSelectAll, onClear, onDecide }: ToolsProps): ReactElement {
  const count = selected.size;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button loading={selecting} loadingLabel="Selecting..." onClick={onSelectAll}>
        {`Select all ${String(group.count)} in this group`}
      </Button>
      {count > 0 ? (
        <>
          <span className="font-semibold text-text">{`${String(count)} of ${String(group.count)} selected`}</span>
          <Button disabled={busy} onClick={() => { onDecide("approved"); }} variant="primary">
            {`Approve selected (${String(count)})`}
          </Button>
          <Button disabled={busy} onClick={() => { onDecide("rejected"); }}>
            {`Keep selected in place (${String(count)})`}
          </Button>
          <Button onClick={onClear} variant="ghost">
            Clear selection
          </Button>
        </>
      ) : null}
    </div>
  );
}

function idsOf(pages: { items: PlanItem[] }[]): number[] {
  return pages.flatMap((page) => page.items.map((row) => row.id));
}

type Items = ReturnType<typeof usePlanItems>;

/** Fetches the pages that are not loaded yet, one after the other, then selects every mail of the group. */
function useSelectAll(items: Items, key: string, onSelection: GroupPanelProps["onSelection"]): { selecting: boolean; selectAll: () => void } {
  const [selecting, setSelecting] = useState(false);
  const run = async (): Promise<void> => {
    setSelecting(true);
    let current = { pages: items.data?.pages ?? [], more: items.hasNextPage };
    for (let step = 0; current.more && step < MAX_PAGES; step += 1) {
      const result = await items.fetchNextPage();
      current = { pages: result.data?.pages ?? current.pages, more: result.hasNextPage && !result.isError };
    }
    const all = new Set(idsOf(current.pages));
    onSelection(key, () => all);
    setSelecting(false);
  };
  return { selecting, selectAll: () => void run() };
}

interface BodyProps {
  items: Items;
  title: string;
  selected: ReadonlySet<number>;
  onToggle: (id: number) => void;
}

function Body({ items, title, selected, onToggle }: BodyProps): ReactElement {
  const rows = items.data?.pages.flatMap((page) => page.items) ?? [];
  if (items.isPending) {
    return <Skeleton />;
  }
  if (items.isError && rows.length === 0) {
    return (
      <div className="mt-3">
        <Banner action={{ label: "Try again", onClick: () => void items.refetch() }} kind="danger" title="Could not load these mails.">
          Check your connection and try again.
        </Banner>
      </div>
    );
  }
  return (
    <>
      {rows.length === 0 ? <p className="mt-3 text-text-muted">No mails in this group.</p> : null}
      <ul aria-label={`Mails in ${title}`} className="mt-3">
        {rows.map((row) => (
          <ReviewItem checked={selected.has(row.id)} key={row.id} onToggle={onToggle} row={row} />
        ))}
      </ul>
      {items.hasNextPage ? (
        <div className="mt-3">
          <Button loading={items.isFetchingNextPage} loadingLabel="Loading..." onClick={() => void items.fetchNextPage()}>
            Load more
          </Button>
        </div>
      ) : null}
    </>
  );
}

/**
 * The opened group: its mails in pages of 100 with Load more, the tick boxes and what can be done with the ticked
 * ones. Rows are keyed by id and memoised, so loading another page or ticking a box leaves the other rows (and the
 * focus) alone. "Select all" only selects; nothing is decided until a decision button is pressed (AC-13).
 */
export function GroupPanel({ group, title, selected, busy, onSelection, onDecideSelected }: GroupPanelProps): ReactElement {
  const items = usePlanItems({ from: group.from, to: group.to }, true);
  const key = groupKey(group);
  const { selecting, selectAll } = useSelectAll(items, key, onSelection);
  const toggle = useCallback(
    (id: number) => {
      onSelection(key, toggled(id));
    },
    [onSelection, key],
  );
  return (
    <div className="mt-3">
      <Tools
        busy={busy}
        group={group}
        onClear={() => {
          onSelection(key, () => new Set());
        }}
        onDecide={(decision) => {
          onDecideSelected(group, decision, [...selected]);
        }}
        onSelectAll={selectAll}
        selected={selected}
        selecting={selecting}
      />
      <Body items={items} onToggle={toggle} selected={selected} title={title} />
    </div>
  );
}
