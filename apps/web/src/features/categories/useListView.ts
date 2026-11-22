import { useState } from "react";

import { ancestorsOf } from "@/features/categories/tree";
import type { ListFilter } from "@/features/categories/tree";

export interface ListView {
  filter: ListFilter;
  setQuery: (query: string) => void;
  setNotifyOnly: (on: boolean) => void;
  /** The paths of the parents that are open. */
  expanded: ReadonlySet<string>;
  toggle: (path: string) => void;
  /** Opens the parents of a category name, so its row can be seen. */
  reveal: (name: string) => void;
}

/** What the list remembers while the edit view is open: the search, the filter and which parents are open. */
export function useListView(): ListView {
  const [query, setQuery] = useState("");
  const [notifyOnly, setNotifyOnly] = useState(false);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  return {
    filter: { query, notifyOnly },
    setQuery,
    setNotifyOnly,
    expanded,
    toggle: (path) => {
      setExpanded((current) => {
        const next = new Set(current);
        if (!next.delete(path)) {
          next.add(path);
        }
        return next;
      });
    },
    reveal: (name) => {
      setExpanded((current) => new Set([...current, ...ancestorsOf(name)]));
    },
  };
}
