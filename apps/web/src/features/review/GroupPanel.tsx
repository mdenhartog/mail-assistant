import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";

import { usePlanItems } from "@/api/plan/plan.queries";
import type { Decision, ItemFilter, ItemSort, PlanGroup, PlanItem } from "@/api/plan/plan.types";
import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { ItemFilterBar } from "@/features/review/ItemFilterBar";
import { ReviewItem } from "@/features/review/ReviewItem";
import { groupKey } from "@/features/review/text";

/** Pages are 100 items and the API allows 100 pages; the loop never runs longer than that. */
const MAX_PAGES = 100;

const NO_MATCH_TEXT = "No mail from that sender in this group";
/** How long the user must stop typing before the search is asked for. */
const DEBOUNCE_MS = 300;

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
  /** True while a sender is searched: "Select all" then asks about the matching mails only. */
  matching: boolean;
  selected: ReadonlySet<number>;
  busy: boolean;
  selecting: boolean;
  onSelectAll: () => void;
  onClear: () => void;
  onDecide: (decision: Decision) => void;
}

function Tools({ group, matching, selected, busy, selecting, onSelectAll, onClear, onDecide }: ToolsProps): ReactElement {
  const count = selected.size;
  const none = count === 0 || busy;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button loading={selecting} loadingLabel="Selecting..." onClick={onSelectAll}>
        {matching ? "Select the mails that match" : `Select all ${String(group.count)} in this group`}
      </Button>
      <span className="font-semibold text-text">{`${String(count)} of ${String(group.count)} selected`}</span>
      <Button disabled={none} onClick={() => { onDecide("approved"); }} variant="primary">
        {`Approve selected (${String(count)})`}
      </Button>
      <Button disabled={none} onClick={() => { onDecide("rejected"); }}>
        {`Keep selected in place (${String(count)})`}
      </Button>
      <Button disabled={count === 0} onClick={onClear} variant="ghost">
        Clear selection
      </Button>
    </div>
  );
}

function idsOf(pages: { items: PlanItem[] }[]): number[] {
  return pages.flatMap((page) => page.items.map((row) => row.id));
}

type Items = ReturnType<typeof usePlanItems>;

/** Fetches the pages that are not loaded yet, one after the other, then hands over the ids of every mail in the list. */
function useSelectAll(items: Items, onDone: (ids: Set<number>) => void): { selecting: boolean; selectAll: () => void } {
  const [selecting, setSelecting] = useState(false);
  const run = async (): Promise<void> => {
    setSelecting(true);
    let current = { pages: items.data?.pages ?? [], more: items.hasNextPage };
    for (let step = 0; current.more && step < MAX_PAGES; step += 1) {
      const result = await items.fetchNextPage();
      current = { pages: result.data?.pages ?? current.pages, more: result.hasNextPage && !result.isError };
    }
    onDone(new Set(idsOf(current.pages)));
    setSelecting(false);
  };
  return { selecting, selectAll: () => void run() };
}

function EmptyText({ searching }: { searching: boolean }): ReactElement {
  return <p className="mt-3 text-text-muted">{searching ? NO_MATCH_TEXT : "No mails in this group."}</p>;
}

interface BodyProps {
  items: Items;
  searching: boolean;
  title: string;
  selected: ReadonlySet<number>;
  onToggle: (id: number) => void;
}

function Body({ items, searching, title, selected, onToggle }: BodyProps): ReactElement {
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
      {rows.length === 0 ? <EmptyText searching={searching} /> : null}
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

function useDebounced(value: string, ms: number): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => {
      setSettled(value);
    }, ms);
    return () => {
      clearTimeout(timer);
    };
  }, [value, ms]);
  return value === "" ? "" : settled;
}

/** "2 mails match", or "At least 100 mails match" while more pages wait. */
function matchText(count: number, more: boolean): string {
  if (more) {
    return `At least ${String(count)} mails match`;
  }
  return count === 1 ? "1 mail matches" : `${String(count)} mails match`;
}

interface AskProps {
  count: number;
  onYes: () => void;
  onNo: () => void;
}

/** The count of the matching mails, named before they are selected. */
function SelectMatchingAsk({ count, onYes, onNo }: AskProps): ReactElement {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 rounded-control border-2 border-border p-3" role="group" aria-label="Select the matching mails">
      <p className="m-0 font-semibold text-text">{`Select all ${String(count)} mails that match?`}</p>
      <Button onClick={onYes} variant="primary">
        {`Select these ${String(count)} mails`}
      </Button>
      <Button onClick={onNo} variant="ghost">
        Not now
      </Button>
    </div>
  );
}

/** The text and the sort the user chose, and the filter that is asked for once typing has paused. */
function useItemFilter(): { text: string; sort: ItemSort; setText: (text: string) => void; setSort: (sort: ItemSort) => void; applied: ItemFilter } {
  const [text, setText] = useState("");
  const [sort, setSort] = useState<ItemSort>("default");
  const sender = useDebounced(text.trim(), DEBOUNCE_MS);
  return { text, sort, setText, setSort, applied: { sender, sort } };
}

function MatchCount({ items }: { items: Items }): ReactElement | null {
  if (items.isPending || items.isError) {
    return null;
  }
  const shown = items.data.pages.reduce((sum, page) => sum + page.items.length, 0);
  return (
    <p className="mt-3 font-semibold text-text" role="status">
      {matchText(shown, items.hasNextPage)}
    </p>
  );
}

/**
 * The opened group: a sender search and a sort choice, its mails in pages of 100 with Load more, the tick boxes and
 * what can be done with the ticked ones. Rows are keyed by id and memoised, so loading another page or ticking a box
 * leaves the other rows (and the focus) alone. "Select all" only selects; nothing is decided until a decision button is
 * pressed (AC-13). While a sender is searched, "Select all" first names how many mails match and then selects only them.
 */
export function GroupPanel({ group, title, selected, busy, onSelection, onDecideSelected }: GroupPanelProps): ReactElement {
  const filter = useItemFilter();
  const items = usePlanItems({ from: group.from, to: group.to }, true, filter.applied);
  const key = groupKey(group);
  const searching = filter.applied.sender !== "";
  const [matches, setMatches] = useState<Set<number> | null>(null);
  const { selecting, selectAll } = useSelectAll(items, (ids) => {
    if (searching) {
      setMatches(ids.size === 0 ? null : ids);
    } else {
      onSelection(key, () => ids);
    }
  });
  useEffect(() => {
    setMatches(null);
  }, [filter.applied.sender]);
  const toggle = useCallback(
    (id: number) => {
      onSelection(key, toggled(id));
    },
    [onSelection, key],
  );
  return (
    <div className="mt-3">
      <ItemFilterBar onSort={filter.setSort} onText={filter.setText} sort={filter.sort} text={filter.text} />
      <Tools
        busy={busy}
        group={group}
        matching={searching}
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
      {matches === null ? null : (
        <SelectMatchingAsk
          count={matches.size}
          onNo={() => {
            setMatches(null);
          }}
          onYes={() => {
            onSelection(key, () => matches);
            setMatches(null);
          }}
        />
      )}
      {searching ? <MatchCount items={items} /> : null}
      <Body items={items} onToggle={toggle} searching={searching} selected={selected} title={title} />
    </div>
  );
}
